from argparse import ArgumentParser
import itertools
from pathlib import Path
import pickle

import iris
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import linregress

import cosmic.WP2.diurnal_cycle_analysis as dca
from basmati.hydrosheds import load_hydrobasins_geodataframe
from cosmic.task import Task, TaskControl
from cosmic.fourier_series import FourierSeries
from cosmic.util import build_raster_cube_from_cube, load_cmap_data, circular_rmse, rmse
from paths import PATHS

SCALES = {
    'small': (2_000, 20_000),
    'medium': (20_000, 200_000),
    'large': (200_000, 2_000_000),
}
N_SLIDING_SCALES = 11
SLIDING_LOWER = np.exp(np.linspace(np.log(2_000), np.log(200_000), N_SLIDING_SCALES))
SLIDING_UPPER = np.exp(np.linspace(np.log(20_000), np.log(2_000_000), N_SLIDING_SCALES))

SLIDING_SCALES = dict([(f'S{i}', (SLIDING_LOWER[i], SLIDING_UPPER[i])) for i in range(N_SLIDING_SCALES)])

MODES = ['amount', 'freq', 'intensity']
DATASETS = ['cmorph', 'u-ak543', 'u-al508', 'HadGEM3-GC31-HM', 'HadGEM3-GC31-MM', 'HadGEM3-GC31-LM']


def savefig(filename):
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)
    print(f'  save fig: {filename}')
    plt.savefig(f'{filename}')
    plt.close('all')


def load_dataset(dataset, mode='amount'):
    if dataset == 'cmorph':
        cmorph_path = (PATHS['datadir'] /
                       'cmorph_data/8km-30min/cmorph_ppt_jja.199801-201812.asia_precip.ppt_thresh_0p1.N1280.nc')
        cmorph_cube = iris.load_cube(str(cmorph_path), f'{mode}_of_precip_jja')
        return cmorph_cube
    elif dataset[:2] == 'u-':
        um_path = (PATHS['datadir'] /
                   f'{dataset}/ap9.pp/{dataset[2:]}a.p9jja.200502-200901.asia_precip.ppt_thresh_0p1.nc')
        um_cube = iris.load_cube(str(um_path), f'{mode}_of_precip_jja')
        return um_cube
    elif dataset[:7] == 'HadGEM3':
        hadgem_path = (PATHS['datadir'] /
                       f'PRIMAVERA_HighResMIP_MOHC/local/{dataset}/{dataset}.highresSST-present.'
                       f'r1i1p1f1.2005-2009.JJA.asia_precip.N1280.ppt_thresh_0p1.nc')
        hadgem_cube = iris.load_cube(str(hadgem_path), f'{mode}_of_precip_JJA')
        return hadgem_cube


def gen_hydrobasins_raster_cubes(inputs, outputs, scales=SCALES):
    diurnal_cycle_cube = load_dataset(DATASETS[0], )
    hydrosheds_dir = PATHS['hydrosheds_dir']
    hb = load_hydrobasins_geodataframe(hydrosheds_dir, 'as', range(1, 9))
    raster_cubes = []
    for scale, (min_area, max_area) in scales.items():
        hb_filtered = hb.area_select(min_area, max_area)
        raster_cube = build_raster_cube_from_cube(diurnal_cycle_cube, hb_filtered, f'hydrobasins_raster_{scale}')
        raster_cubes.append(raster_cube)
    raster_cubes = iris.cube.CubeList(raster_cubes)
    iris.save(raster_cubes, str(outputs[0]))


def gen_basin_vector_area_avg(inputs, outputs, diurnal_cycle_cube, raster, method):
    phase_mag = dca.calc_vector_area_avg(diurnal_cycle_cube, raster, method)
    df = pd.DataFrame(phase_mag, columns=['phase', 'magnitude'])
    df.to_hdf(outputs[0], outputs[0].stem)


def gen_basin_area_avg_phase_mag(inputs, outputs, diurnal_cycle_cube, raster, method):
    lon = diurnal_cycle_cube.coord('longitude').points
    lat = diurnal_cycle_cube.coord('latitude').points
    dc_basins = []
    lons = np.repeat(lon[None, :], len(lat), axis=0)
    step_length = 24 / diurnal_cycle_cube.shape[0]
    dc_phase_LST = []
    dc_peak = []

    for i in range(1, raster.max() + 1):
        dc_basin = []
        for t_index in range(diurnal_cycle_cube.shape[0]):
            dc_basin.append(diurnal_cycle_cube.data[t_index][raster == i].mean())
        dc_basin = np.array(dc_basin)
        dc_basins.append(dc_basin)
        basin_lon = lons[raster == i].mean()

        t_offset = basin_lon / 180 * 12
        if method == 'peak':
            phase_GMT = dc_basin.argmax() * step_length
            mag = dc_basin.max() / dc_basin.mean() - 1
        elif method == 'harmonic':
            fs = FourierSeries(np.linspace(0, 24 - step_length, diurnal_cycle_cube.shape[0]))
            fs.fit(dc_basin, 1)
            phases, amp = fs.component_phase_amp(1)
            phase_GMT = phases[0]
            mag = amp
        else:
            raise Exception(f'Unknown method: {method}')
        dc_phase_LST.append((phase_GMT + t_offset + step_length / 2) % 24)
        dc_peak.append(mag)
    dc_phase_LST = np.array(dc_phase_LST)
    dc_peak = np.array(dc_peak)

    phase_mag = np.stack([dc_phase_LST, dc_peak], axis=1)
    df = pd.DataFrame(phase_mag, columns=['phase', 'magnitude'])
    df.to_hdf(outputs[0], outputs[0].stem)


def gen_phase_mag_map(inputs, outputs, diurnal_cycle_cube, raster):
    df_phase_mag = pd.read_hdf(inputs[0], inputs[0].stem)
    # Use phase_mag and raster to make 2D maps.
    phase_mag = df_phase_mag.values
    phase_map = np.zeros_like(raster, dtype=float)
    mag_map = np.zeros_like(raster, dtype=float)
    for i in range(1, raster.max() + 1):
        phase_map[raster == i] = phase_mag[i - 1, 0]
        mag_map[raster == i] = phase_mag[i - 1, 1]
    phase_map_cube = iris.cube.Cube(phase_map, long_name='phase_map', units='hr',
                                    dim_coords_and_dims=[(diurnal_cycle_cube.coord('latitude'), 0),
                                                         (diurnal_cycle_cube.coord('longitude'), 1)])
    mag_map_cube = iris.cube.Cube(mag_map, long_name='magnitude_map', units='-',
                                  dim_coords_and_dims=[(diurnal_cycle_cube.coord('latitude'), 0),
                                                       (diurnal_cycle_cube.coord('longitude'), 1)])
    cubes = iris.cube.CubeList([phase_map_cube, mag_map_cube])
    iris.save(cubes, str(outputs[0]))


def plot_phase_cmorph_vs_datasets_ax(ax, rmses, xticks):
    for dataset, (phase_rmses, mag_rmses) in rmses.items():
        ax.plot(phase_rmses, label=dataset)

    ax.set_xlabel('basin scale (km$^2$)')
    ax.set_ylabel('circular RMSE (hr)')
    ax.set_ylim((0, 5))
    ax.set_xticks(xticks, ['2000 - 20000', '20000 - 200000', '200000 - 2000000'])


def plot_mag_cmorph_vs_datasets_ax(ax, rmses, xticks):
    for dataset, (phase_rmses, mag_rmses) in rmses.items():
        ax.plot(mag_rmses, label=dataset)

    ax.set_xlabel('basin scale (km$^2$)')
    ax.set_ylabel('RMSE (-)')
    ax.set_xticks(xticks, ['2000 - 20000', '20000 - 200000', '200000 - 2000000'])


def plot_cmorph_vs_all_datasets(inputs, outputs, rmses, xticks):
    both_filename = outputs[0]
    fig, axes = plt.subplots(2, 3, sharex=True, num=str(both_filename), figsize=(12, 8))
    for i, mode in enumerate(rmses.keys()):
        ax1 = axes[0, i]
        ax2 = axes[1, i]
        ax1.set_ylim((0, 5))
        rmses_for_mode = rmses[mode]
        for dataset, (phase_rmses, mag_rmses) in rmses_for_mode.items():
            ax1.plot(phase_rmses, label=dataset)
            ax2.plot(mag_rmses, label=dataset)
        ax2.set_xticks(xticks)
        ax2.set_xticklabels(['2000 - 20000', '20000 - 200000', '200000 - 2000000'])
    axes[0, 0].set_title('Amount')
    axes[0, 1].set_title('Frequency')
    axes[0, 2].set_title('Intensity')
    axes[0, 0].set_ylabel('phase\ncircular RMSE (hr)')
    axes[1, 0].set_ylabel('phase\nRMSE (-)')
    axes[1, 1].set_xlabel('basin scale (km$^2$)')
    axes[1, 0].legend()
    plt.tight_layout()
    savefig(both_filename)


def plot_cmorph_vs_all_datasets2(inputs, outputs, mode, rmses_for_mode, xticks):
    phase_filename, mag_filename = outputs
    plt.figure(str(phase_filename))
    plt.clf()
    ax = plt.gca()
    ax.set_title(f'Diurnal cycle of {mode} phase compared to CMORPH')
    plot_phase_cmorph_vs_datasets_ax(ax, rmses_for_mode, xticks)
    ax.legend()
    savefig(phase_filename)

    plt.figure(str(mag_filename))
    plt.clf()
    ax = plt.gca()
    ax.set_title(f'Diurnal cycle of {mode} strength compared to CMORPH')
    plot_mag_cmorph_vs_datasets_ax(ax, rmses_for_mode, xticks)
    ax.legend()
    savefig(mag_filename)


def plot_phase_mag(inputs, outputs, basin_scale, mode, raster_cube, row):
    phase_filename, mag_filename = outputs
    print(f'Plot maps - {basin_scale}_{mode}: {row.dataset}_{row.task.outputs[0]}')
    cmap, norm, bounds, cbar_kwargs = load_cmap_data('cmap_data/li2018_fig3_cb.pkl')
    phase_mag_cubes = row.task.load_output()
    phase_map = phase_mag_cubes.extract_strict('phase_map')
    mag_map = phase_mag_cubes.extract_strict('magnitude_map')
    lon = phase_map.coord('longitude').points
    lat = phase_map.coord('latitude').points
    extent = tuple(lon[[0, -1]]) + tuple(lat[[0, -1]])
    plt.figure(f'{row.dataset}_{row.task.outputs[0]}_phase', figsize=(10, 8))
    plt.clf()
    plt.title(f'{row.dataset}: {row.analysis_order}_{row.method} phase')
    plt.imshow(np.ma.masked_array(phase_map.data, raster_cube.data == 0),
               cmap=cmap, norm=norm,
               origin='lower', extent=extent, vmin=0, vmax=24)
    plt.colorbar(orientation='horizontal')
    plt.tight_layout()
    savefig(phase_filename)
    plt.figure(f'{row.task.outputs[0]}_magnitude', figsize=(10, 8))
    plt.clf()
    plt.title(f'{row.dataset}: {row.analysis_order}_{row.method} magnitude')
    plt.imshow(np.ma.masked_array(mag_map.data, raster_cube.data == 0),
               origin='lower', extent=extent)
    plt.colorbar(orientation='horizontal')
    plt.tight_layout()
    savefig(mag_filename)


def plot_dataset_scatter(inputs, outputs, basin_scale, mode, row1, row2):
    phase_scatter_filename, mag_scatter_filename = outputs
    title = f'{basin_scale}_{mode}_{row1.dataset}_{row1.analysis_order}_{row1.method}-' \
            f'{row2.dataset}_{row2.analysis_order}_{row2.method}'
    print(f'Plot comparison - {title}')
    phase_mag1 = row1.task.load_output()
    phase_mag2 = row2.task.load_output()
    plt.figure(f'{title}_phase_scatter', figsize=(10, 8))
    plt.clf()
    use_sin = False
    if use_sin:
        data1 = np.sin(phase_mag1.values[:, 0] * 2 * np.pi / 24)
        data2 = np.sin(phase_mag2.values[:, 0] * 2 * np.pi / 24)
    else:
        data1, data2 = phase_mag1.values[:, 0], phase_mag2.values[:, 0]
    plt.title(f'phase: {row1.dataset}_{row1.analysis_order}_{row1.method} - '
              f'{row2.dataset}_{row2.analysis_order}_{row2.method}')
    plt.scatter(data1, data2)
    plt.xlabel(f'{row1.dataset}_{row1.analysis_order}_{row1.method}')
    plt.ylabel(f'{row2.dataset}_{row2.analysis_order}_{row2.method}')
    if use_sin:
        plt.xlim((-1, 1))
        plt.ylim((-1, 1))
        plt.plot([-1, 1], [-1, 1])
        x = np.array([-1, 1])
    else:
        plt.xlim((0, 24))
        plt.ylim((0, 24))
        plt.plot([0, 24], [0, 24])
        x = np.array([0, 24])
    phase_regress = linregress(data1, data2)
    y = phase_regress.slope * x + phase_regress.intercept
    plt.plot(x, y, 'r--')
    savefig(phase_scatter_filename)
    plt.figure(f'{title}_mag_scatter', figsize=(10, 8))
    plt.clf()
    plt.title(f'mag: {row1.dataset}_{row1.analysis_order}_{row1.method} - '
              f'{row2.dataset}_{row2.analysis_order}_{row2.method}')
    plt.scatter(phase_mag1['magnitude'], phase_mag2['magnitude'])
    plt.xlabel(f'{row1.dataset}_{row1.analysis_order}_{row1.method}')
    plt.ylabel(f'{row2.dataset}_{row2.analysis_order}_{row2.method}')
    # max_val = max(phase_mag1['magnitude'].max(), phase_mag2['magnitude'].max())
    max_val = 0.5
    plt.xlim((0, max_val))
    plt.ylim((0, max_val))
    plt.plot([0, max_val], [0, max_val])
    mag_regress = linregress(phase_mag1['magnitude'], phase_mag2['magnitude'])
    y = mag_regress.slope * x + mag_regress.intercept
    plt.plot(x, y, 'r--')
    savefig(mag_scatter_filename)


class DiurnalCycleAnalysis:
    def __init__(self, raster_scales='small_medium_large', force=False):
        self.analysis_task_ctrl = TaskControl()
        self.fig_task_ctrl = TaskControl()
        self.raster_scales = raster_scales
        if self.raster_scales == 'small_medium_large':
            self.scales = SCALES
        elif self.raster_scales == 'sliding':
            self.scales = SLIDING_SCALES
        self.force = force
        self.df_keys = None
        self.figsdir = PATHS['figsdir'] / 'basin_diurnal_cycle_analysis'
        self.figsdir.mkdir(parents=True, exist_ok=True)
        self.keys = []
        self.prev_lon, self.prev_lat = None, None
        self.ordered_raster_cubes = []

    def load_ordered_raster_cubes(self):
        hb_raster_cubes_fn = f'data/basin_diurnal_cycle_analysis/hb_N1280_raster_{self.raster_scales}.nc'
        hb_raster_cubes_task = Task(gen_hydrobasins_raster_cubes, [], [hb_raster_cubes_fn],
                                    fn_args=[self.scales])
        hb_raster_cubes = hb_raster_cubes_task.run().load_output()
        self.ordered_raster_cubes = [hb_raster_cubes.extract_strict(f'hydrobasins_raster_{s}') for s in self.scales]

    def gen_analysis_tasks(self, dataset, mode):
        if not self.ordered_raster_cubes:
            self.load_ordered_raster_cubes()

        print(f'Dataset, mode: {dataset}, {mode}')
        diurnal_cycle_cube = load_dataset(dataset, mode)
        # Verify all longitudes/latitudes are the same.
        lon = diurnal_cycle_cube.coord('longitude').points
        lat = diurnal_cycle_cube.coord('latitude').points
        if self.prev_lon is not None and self.prev_lat is not None:
            assert (lon == self.prev_lon).all() and (lat == self.prev_lat).all()
        self.prev_lon, self.prev_lat = lon, lat

        for raster_cube, method in itertools.product(self.ordered_raster_cubes,
                                                     ['peak', 'harmonic']):
            print(f'  raster_cube, method: {raster_cube.name()}, {method}')
            self.basin_vector_area_avg(dataset, diurnal_cycle_cube, raster_cube, method, mode)
            self.basin_area_avg(dataset, diurnal_cycle_cube, raster_cube, method, mode)

    def run_all(self):
        for dataset, mode in itertools.product(DATASETS, MODES):
            self.gen_analysis_tasks(dataset, mode)

        self.analysis_task_ctrl.finilize()
        self.df_keys = self.analysis_task_ctrl.index

        for raster_cube, mode in itertools.product(self.ordered_raster_cubes, MODES):
            self.gen_fig_tasks(raster_cube, mode)

        self.gen_cmorph_vs_datasets_fig_tasks()

        self.analysis_task_ctrl.run(self.force)
        self.fig_task_ctrl.finilize().run(self.force)

    def gen_rmses(self, inputs, outputs):
        rmses = {}

        for mode in MODES:
            selector = ((self.df_keys.method == 'harmonic') &
                        (self.df_keys.type == 'phase_mag_cubes') &
                        (self.df_keys.analysis_order == 'basin_area_avg') &
                        (self.df_keys['mode'] == mode))

            df_cmorph = self.df_keys[selector & (self.df_keys.dataset == 'cmorph')]

            rmses_for_mode = {}

            for dataset in DATASETS[1:]:
                phase_rmses = []
                mag_rmses = []
                df_dataset = self.df_keys[selector & (self.df_keys.dataset == dataset)]
                for raster, scale in zip(self.ordered_raster_cubes, self.scales):
                    cmorph_phase_mag = (df_cmorph[df_cmorph.basin_scale == f'hydrobasins_raster_{scale}']
                                        .task.values[0].load_output())
                    dataset_phase_mag = (df_dataset[df_dataset.basin_scale == f'hydrobasins_raster_{scale}']
                                         .task.values[0].load_output())

                    cmorph_phase = cmorph_phase_mag.extract_strict('phase_map')
                    cmorph_mag = cmorph_phase_mag.extract_strict('magnitude_map')

                    dataset_phase = dataset_phase_mag.extract_strict('phase_map')
                    dataset_mag = dataset_phase_mag.extract_strict('magnitude_map')

                    phase_rmses.append(circular_rmse(cmorph_phase.data[raster != 0],
                                                     dataset_phase.data[raster != 0]))
                    mag_rmses.append(rmse(cmorph_mag.data[raster != 0],
                                          dataset_mag.data[raster != 0]))
                rmses_for_mode[dataset] = (phase_rmses, mag_rmses)
            rmses[mode] = rmses_for_mode
        pickle.dump(rmses, outputs[0])

    def gen_cmorph_vs_datasets_fig_tasks(self):
        rmses_filename = Path(f'data/rmses_{self.raster_scales}.pkl')
        rmses = Task(self.gen_rmses, [], [rmses_filename]).run().load_output()

        if self.raster_scales == 'small_medium_large':
            xticks = [0, 1, 2]
        elif self.raster_scales == 'sliding':
            xticks = [0, 5, 10]
        both_filename = Path(f'{self.figsdir}/cmorph_vs/{self.raster_scales}/'
                             f'cmorph_vs_datasets.all.phase_and_mag.png')
        self.fig_task_ctrl.add(Task(plot_cmorph_vs_all_datasets, [], [both_filename],
                                    fn_args=[rmses, xticks]))

        for mode, rmses_for_mode in rmses.items():
            phase_filename = Path(f'{self.figsdir}/cmorph_vs/{self.raster_scales}/'
                                  f'cmorph_vs_datasets.{mode}.phase.circular_rmse.png')
            mag_filename = Path(f'{self.figsdir}/cmorph_vs/{self.raster_scales}/'
                                f'cmorph_vs_datasets.{mode}.mag.rmse.png')
            self.fig_task_ctrl.add(Task(plot_cmorph_vs_all_datasets2, [], [phase_filename, mag_filename],
                                        fn_args=[mode, rmses_for_mode, xticks]))

    def basin_vector_area_avg(self, dataset, diurnal_cycle_cube, raster_cube, method, mode):
        raster = raster_cube.data
        fn_base = f'data/basin_diurnal_cycle_analysis/{dataset}/vector_area_avg_' \
                  f'{diurnal_cycle_cube.name()}_{mode}_{raster_cube.name()}_{method}'
        df_phase_mag_key = f'{fn_base}.hdf'

        task_kwargs = dict(
            dataset=dataset,
            mode=mode,
            basin_scale=raster_cube.name(),
            analysis_order='vector_area_avg',
            method=method,
        )
        phase_mag_task = Task(gen_basin_vector_area_avg, [], [df_phase_mag_key],
                              fn_args=[diurnal_cycle_cube, raster, method],
                              type='phase_mag', **task_kwargs)

        phase_mag_cubes_key = f'{fn_base}.nc'
        phase_mag_cubes_task = Task(gen_phase_mag_map, [df_phase_mag_key], [phase_mag_cubes_key],
                                    fn_args=[diurnal_cycle_cube, raster],
                                    type='phase_mag_cubes', **task_kwargs)
        self.analysis_task_ctrl.add(phase_mag_task)
        self.analysis_task_ctrl.add(phase_mag_cubes_task)

    def basin_area_avg(self, dataset, diurnal_cycle_cube, raster_cube, method, mode):
        raster = raster_cube.data

        fn_base = f'data/basin_diurnal_cycle_analysis/{dataset}/basin_area_avg_' \
                  f'{diurnal_cycle_cube.name()}_{mode}_{raster_cube.name()}_{method}'

        task_kwargs = dict(
            dataset=dataset,
            mode=mode,
            basin_scale=raster_cube.name(),
            analysis_order='basin_area_avg',
            method=method,
        )

        df_phase_mag_key = f'{fn_base}.hdf'
        phase_mag_task = Task(gen_basin_area_avg_phase_mag, [], [df_phase_mag_key],
                              fn_args=[diurnal_cycle_cube, raster, method],
                              type='phase_mag', **task_kwargs)

        phase_mag_cubes_key = f'{fn_base}.nc'
        phase_mag_cubes_task = Task(gen_phase_mag_map, [df_phase_mag_key], [phase_mag_cubes_key],
                                    fn_args=[diurnal_cycle_cube, raster],
                                    type='phase_mag_cubes', **task_kwargs)
        self.analysis_task_ctrl.add(phase_mag_task)
        self.analysis_task_ctrl.add(phase_mag_cubes_task)

    def gen_fig_tasks(self, raster_cube, mode):
        # Loop over datasets for basin_area_avg -> harmonic  for each mode and raster cube.
        for row in [
            ir[1]
            for ir in
            self.df_keys[(self.df_keys['type'] == 'phase_mag_cubes') &
                         (self.df_keys['dataset'] != 'cmorph') &
                         (self.df_keys['analysis_order'] == 'basin_area_avg') &
                         (self.df_keys['basin_scale'] == raster_cube.name()) &
                         (self.df_keys['mode'] == mode) &
                         (self.df_keys['method'] == 'harmonic')
                         ].iterrows()]:
            self.gen_phase_mag_maps_tasks(raster_cube, mode, row)

        # Loop over analysis types for CMORPH for each mode and raster cube.
        for row in [
                ir[1]
                for ir in
                self.df_keys[(self.df_keys['type'] == 'phase_mag_cubes') &
                             (self.df_keys['dataset'] == 'cmorph') &
                             (self.df_keys['basin_scale'] == raster_cube.name()) &
                             (self.df_keys['mode'] == mode)
                             ].iterrows()]:
            self.gen_phase_mag_maps_tasks(raster_cube, mode, row)

        # Loop over datasets for basin_area_avg -> harmonic  for each mode and raster cube.
        phase_mag_rows = [
            ir[1]
            for ir in
            self.df_keys[(self.df_keys['type'] == 'phase_mag') &
                         (self.df_keys['analysis_order'] == 'basin_area_avg') &
                         (self.df_keys['basin_scale'] == raster_cube.name()) &
                         (self.df_keys['method'] == 'harmonic') &
                         (self.df_keys['mode'] == mode)
                         ].iterrows()]

        for row1, row2 in itertools.combinations(phase_mag_rows, 2):
            self.gen_dataset_comparison_tasks(raster_cube, mode, row1, row2)

        # Loop over analysis types for CMORPH for each mode and raster cube.
        phase_mag_rows2 = [
            ir[1]
            for ir in
            self.df_keys[(self.df_keys['type'] == 'phase_mag') &
                         (self.df_keys['dataset'] == 'cmorph') &
                         (self.df_keys['basin_scale'] == raster_cube.name()) &
                         (self.df_keys['mode'] == mode)
                         ].iterrows()]

        for row1, row2 in itertools.combinations(phase_mag_rows2, 2):
            self.gen_dataset_comparison_tasks(raster_cube, mode, row1, row2)

    def gen_phase_mag_maps_tasks(self, raster_cube, mode, row):
        basin_scale = raster_cube.name().split('_')[-1]
        phase_filename = Path(f'{self.figsdir}/map/{mode}/{row.dataset}_{row.analysis_order}_{row.method}'
                              f'.{basin_scale}.phase.png')
        mag_filename = Path(f'{self.figsdir}/map/{mode}/{row.dataset}_{row.analysis_order}_{row.method}'
                            f'.{basin_scale}.mag.png')
        self.fig_task_ctrl.add(Task(plot_phase_mag, [], [phase_filename, mag_filename],
                                    fn_args=[basin_scale, mode, raster_cube, row]))

    def gen_dataset_comparison_tasks(self, raster_cube, mode, row1, row2):
        basin_scale = raster_cube.name().split('_')[-1]
        phase_scatter_filename = Path(f'{self.figsdir}/comparison/{mode}/'
                                      f'{row1.dataset}_{row1.analysis_order}_{row1.method}_vs_'
                                      f'{row2.dataset}_{row2.analysis_order}_{row2.method}.'
                                      f'{basin_scale}.phase.png')
        mag_scatter_filename = Path(f'{self.figsdir}/comparison/{mode}/'
                                    f'{row1.dataset}_{row1.analysis_order}_{row1.method}_vs_'
                                    f'{row2.dataset}_{row2.analysis_order}_{row2.method}.'
                                    f'{basin_scale}.mag.png')

        self.fig_task_ctrl.add(Task(plot_dataset_scatter, [], [phase_scatter_filename, mag_scatter_filename],
                                    fn_args=[basin_scale, mode, row1, row2]))


def run_analysis(scales, force):
    analysis = DiurnalCycleAnalysis(scales, force)
    analysis.run_all()


def basin_analysis_all():
    yield run_analysis, ['small_medium_large', False], {}
    yield run_analysis, ['sliding', False], {}


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--scales', default='small_medium_large', choices=['small_medium_large', 'sliding'])
    args = parser.parse_args()
    run_analysis(args.scales, args.force)
