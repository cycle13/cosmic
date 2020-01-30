import itertools
from pathlib import Path

import iris
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import linregress

import cosmic.WP2.diurnal_cycle_analysis as dca
from basmati.hydrosheds import load_hydrobasins_geodataframe
from cosmic.filestore import FileStore
from cosmic.fourier_series import FourierSeries
from cosmic.util import build_raster_cube_from_cube, load_cmap_data
from paths import PATHS

SCALES = ['small', 'medium', 'large']
MODES = ['amount', 'freq', 'intensity']
DATASETS = ['cmorph', 'u-ak543', 'u-al508', 'HadGEM3-GC31-HM', 'HadGEM3-GC31-MM', 'HadGEM3-GC31-LM']


def savefig(filename):
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)
    print(f'  save fig: {filename}')
    plt.savefig(f'{filename}')
    plt.close('all')


def gen_hydrobasins_raster_cubes(diurnal_cycle_cube):
    hydrosheds_dir = PATHS['hydrosheds_dir']
    hb = load_hydrobasins_geodataframe(hydrosheds_dir, 'as', range(1, 9))
    raster_cubes = []
    min_area, max_area = 0, 1_000_000_000
    for scale in SCALES:
        if scale == 'small':
            min_area, max_area = 2_000, 20_000
        elif scale == 'medium':
            min_area, max_area = 20_000, 200_000
        elif scale == 'large':
            min_area, max_area = 200_000, 2_000_000
        hb_filtered = hb.area_select(min_area, max_area)
        raster_cube = build_raster_cube_from_cube(diurnal_cycle_cube, hb_filtered, f'hydrobasins_raster_{scale}')
        raster_cubes.append(raster_cube)
    raster_cubes = iris.cube.CubeList(raster_cubes)
    return raster_cubes


def gen_basin_vector_area_avg(diurnal_cycle_cube, raster, method):
    phase_mag = dca.calc_vector_area_avg(diurnal_cycle_cube, raster, method)
    return pd.DataFrame(phase_mag, columns=['phase', 'magnitude'])


def gen_basin_area_avg_phase_mag(diurnal_cycle_cube, raster, method):
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
    return pd.DataFrame(phase_mag, columns=['phase', 'magnitude'])


def gen_phase_mag_map(df_phase_mag, diurnal_cycle_cube, raster):
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
    return iris.cube.CubeList([phase_map_cube, mag_map_cube])


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


class DiurnalCycleAnalysis:
    def __init__(self, filestore):
        self.filestore = filestore
        self.df_keys = None
        self.figsdir = PATHS['figsdir'] / 'basin_diurnal_cycle_analysis'
        self.figsdir.mkdir(parents=True, exist_ok=True)
        self.keys = []
        self.prev_lon, self.prev_lat = None, None
        self.ordered_raster_cubes = []

    def load_ordered_raster_cubes(self):
        diurnal_cycle_cube = load_dataset(DATASETS[0], )
        hb_raster_cubes = self.filestore('data/hb_N1280_raster_small_medium_large.nc',
                                         gen_hydrobasins_raster_cubes,
                                         gen_fn_args=[diurnal_cycle_cube])
        self.ordered_raster_cubes = [hb_raster_cubes.extract_strict(f'hydrobasins_raster_{s}') for s in SCALES]

    def run(self, dataset, mode):
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
            df_vector_phase_mag_key, vector_phase_mag_cubes_key = \
                self.basin_vector_area_avg(dataset, diurnal_cycle_cube, raster_cube, method, mode)
            self.keys.append([dataset, mode, raster_cube.name(), 'vector_area_avg', method, 'phase_mag',
                              df_vector_phase_mag_key])
            self.keys.append([dataset, mode, raster_cube.name(), 'vector_area_avg', method, 'phase_mag_cubes',
                              vector_phase_mag_cubes_key])

            df_area_phase_mag_key, area_phase_mag_cubes_key = self.basin_area_avg(dataset, diurnal_cycle_cube,
                                                                                  raster_cube, method, mode)
            self.keys.append([dataset, mode, raster_cube.name(), 'basin_area_avg', method, 'phase_mag',
                              df_area_phase_mag_key])
            self.keys.append([dataset, mode, raster_cube.name(), 'basin_area_avg', method, 'phase_mag_cubes',
                              area_phase_mag_cubes_key])

        self.df_keys = pd.DataFrame(self.keys,
                                    columns=['dataset', 'mode', 'basin_scale',
                                             'analysis_order', 'method', 'type', 'key'])

    def run_all(self):
        for dataset, mode in itertools.product(DATASETS, MODES):
            self.run(dataset, mode)

        extent = tuple(self.prev_lon[[0, -1]]) + tuple(self.prev_lat[[0, -1]])
        for raster_cube, mode in itertools.product(self.ordered_raster_cubes, MODES):
            self.plot_output(extent, raster_cube, mode)

    def basin_vector_area_avg(self, dataset, diurnal_cycle_cube, raster_cube, method, mode):
        raster = raster_cube.data

        fn_base = f'data/{dataset}/diurnal_cycle_analysis/vector_area_avg-' \
                  f'{diurnal_cycle_cube.name()}_{mode}_{raster_cube.name()}_{method}'
        df_phase_mag_key = f'{fn_base}.hdf'
        df_phase_mag = self.filestore(
            df_phase_mag_key,
            gen_basin_vector_area_avg,
            gen_fn_args=[diurnal_cycle_cube, raster, method],
        )

        phase_mag_cubes_key = f'{fn_base}.nc'
        self.filestore(
            phase_mag_cubes_key,
            gen_phase_mag_map,
            gen_fn_args=[df_phase_mag, diurnal_cycle_cube, raster],
        )
        return df_phase_mag_key, phase_mag_cubes_key

    def basin_area_avg(self, dataset, diurnal_cycle_cube, raster_cube, method, mode):
        raster = raster_cube.data

        fn_base = f'data/{dataset}/diurnal_cycle_analysis/basin_area_avg-' \
                  f'{diurnal_cycle_cube.name()}_{mode}_{raster_cube.name()}_{method}'

        df_phase_mag_key = f'{fn_base}.hdf'
        df_phase_mag = self.filestore(
            df_phase_mag_key,
            gen_basin_area_avg_phase_mag,
            gen_fn_args=[diurnal_cycle_cube, raster, method],
        )

        phase_mag_cubes_key = f'{fn_base}.nc'
        self.filestore(
            phase_mag_cubes_key,
            gen_phase_mag_map,
            gen_fn_args=[df_phase_mag, diurnal_cycle_cube, raster],
        )
        return df_phase_mag_key, phase_mag_cubes_key

    def plot_output(self, extent, raster_cube, mode):
        # Loop over datasets for basin_area_avg -> harmonic  for each mode and raster cube.
        for row in [
            ir[1]
            for ir in
            self.df_keys[(self.df_keys['type'] == 'phase_mag_cubes') &
                         (self.df_keys['analysis_order'] == 'basin_area_avg') &
                         (self.df_keys['basin_scale'] == raster_cube.name()) &
                         (self.df_keys['mode'] == mode) &
                         (self.df_keys['method'] == 'harmonic')
                         ].iterrows()]:
            self.plot_phase_mag_maps(extent, raster_cube, mode, row)

        # Loop over analysis types for CMORPH for each mode and raster cube.
        for row in [
                ir[1]
                for ir in
                self.df_keys[(self.df_keys['type'] == 'phase_mag_cubes') &
                             (self.df_keys['dataset'] == 'cmorph') &
                             (self.df_keys['basin_scale'] == raster_cube.name()) &
                             (self.df_keys['mode'] == mode)
                             ].iterrows()]:
            self.plot_phase_mag_maps(extent, raster_cube, mode, row)

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
            self.plot_dataset_comparison(raster_cube, mode, row1, row2)

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
            self.plot_dataset_comparison(raster_cube, mode, row1, row2)

    def plot_phase_mag_maps(self, extent, raster_cube, mode, row):
        basin_scale = raster_cube.name().split('_')[-1]
        print(f'Plot maps - {basin_scale}_{mode}: {row.dataset}_{row.key}')
        cmap, norm, bounds, cbar_kwargs = load_cmap_data('cmap_data/li2018_fig3_cb.pkl')

        phase_mag_cubes = self.filestore(row.key)

        phase_map = phase_mag_cubes.extract_strict('phase_map')
        mag_map = phase_mag_cubes.extract_strict('magnitude_map')

        plt.figure(f'{row.dataset}_{row.key}_phase', figsize=(10, 8))
        plt.clf()
        plt.title(f'{row.dataset}: {row.analysis_order}_{row.method} phase')

        plt.imshow(np.ma.masked_array(phase_map.data, raster_cube.data == 0),
                   cmap=cmap, norm=norm,
                   origin='lower', extent=extent, vmin=0, vmax=24)
        plt.colorbar(orientation='horizontal')
        plt.tight_layout()
        savefig(f'{self.figsdir}/map/{mode}/{row.dataset}_{row.analysis_order}_{row.method}'
                f'.{basin_scale}.phase.png')

        plt.figure(f'{row.key}_magnitude', figsize=(10, 8))
        plt.clf()
        plt.title(f'{row.dataset}: {row.analysis_order}_{row.method} magnitude')
        plt.imshow(np.ma.masked_array(mag_map.data, raster_cube.data == 0),
                   origin='lower', extent=extent)
        plt.colorbar(orientation='horizontal')
        plt.tight_layout()
        savefig(f'{self.figsdir}/map/{mode}/{row.dataset}_{row.analysis_order}_{row.method}'
                f'.{basin_scale}.mag.png')

    def plot_dataset_comparison(self, raster_cube, mode, row1, row2):
        basin_scale = raster_cube.name().split('_')[-1]
        print(f'Plot comparison - {basin_scale}_{mode}: {row1.dataset}_{row1.analysis_order}_{row1.method} - '
              f'{row2.dataset}_{row2.analysis_order}_{row2.method}')
        phase_mag1 = self.filestore(row1.key)
        phase_mag2 = self.filestore(row2.key)
        plt.figure(f'{row1.key}_{row2.key}_phase_scatter', figsize=(10, 8))
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
        savefig(f'{self.figsdir}/comparison/{mode}/'
                f'{row1.dataset}_{row1.analysis_order}_{row1.method}_vs_'
                f'{row2.dataset}_{row2.analysis_order}_{row2.method}.'
                f'{basin_scale}.phase.png')
        plt.figure(f'{row1.key}_{row2.key}_mag_scatter', figsize=(10, 8))
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
        savefig(f'{self.figsdir}/comparison/{mode}/'
                f'{row1.dataset}_{row1.analysis_order}_{row1.method}_vs_'
                f'{row2.dataset}_{row2.analysis_order}_{row2.method}.'
                f'{basin_scale}.mag.png')


def basin_analysis_all():
    filestore = FileStore()
    analysis = DiurnalCycleAnalysis(filestore)
    yield (analysis.run_all, [], {})


if __name__ == '__main__':
    try:
        filestore
        # Using ipython: run -i $0.
        print('USING IN-MEM CACHE')
    except NameError:
        filestore = FileStore()
    analysis = DiurnalCycleAnalysis(filestore)
    analysis.run_all()
