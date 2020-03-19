import itertools

import headless_matplotlib
import iris

from cosmic.WP2.afi_base import AFI_basePlotter
from cosmic.WP2.afi_mean_plot import AFI_meanPlotter
from cosmic.WP2.afi_diurnal_cycle_plot import AFI_diurnalCyclePlotter

from remake import TaskControl, Task, remake_required, RemakeOn

from config import PATHS
from seasonal_precip_analysis import fmt_thresh_text


REMAKE_TASK_CTRL_FUNC = 'gen_task_ctrl'

MODES = ['amount', 'freq', 'intensity']


@remake_required(depends_on=[AFI_meanPlotter, AFI_basePlotter])
def fig_afi_mean(inputs, outputs, season, domain, method):
    afi_mean = AFI_meanPlotter(season, domain, method)
    cubes = {}
    for (runid, cube_name), cube_path in inputs.items():
        cubes[(runid, cube_name)] = iris.load_cube(str(cube_path), cube_name)
    afi_mean.set_cubes(cubes)
    afi_mean.plot()
    afi_mean.save(outputs[0])


@remake_required(depends_on=[AFI_diurnalCyclePlotter, AFI_basePlotter])
def fig_afi_diurnal_cycle(inputs, outputs, season, domain, method):
    afi_mean = AFI_diurnalCyclePlotter(season, domain, method)
    cubes = {}
    for (runid, cube_name), cube_path in inputs.items():
        cubes[(runid, cube_name)] = iris.load_cube(str(cube_path), cube_name)
    afi_mean.set_cubes(cubes)
    afi_mean.plot()
    afi_mean.save(outputs[0])


class AfiTask(Task):
    def __init__(self, func, datadir, figsdir, duration, precip_thresh, season, domain, method=None):
        self.runids = ['cmorph_8km', 'ak543', 'al508']
        thresh_text = fmt_thresh_text(precip_thresh)

        inputs = {}

        for runid in self.runids:
            if runid == 'cmorph_8km':
                if duration == 'short':
                    daterange = '200906-200908'
                elif duration == 'long':
                    daterange = '199801-201812'
                rel_path = 'cmorph_data/8km-30min'
                filename = f'cmorph_8km_N1280.{daterange}.{season}.asia_precip_afi.ppt_thresh_{thresh_text}.nc'
                # filename = f'cmorph_ppt_{season}.{daterange}.asia_precip.ppt_thresh_{thresh_text}.N1280.nc'
            else:
                if duration == 'short':
                    daterange = '200806-200808'
                elif duration == 'long':
                    daterange = '200506-200808'

                rel_path = f'u-{runid}/ap9.pp'
                # filename = f'{runid}a.p9{season}.{daterange}.asia_precip.ppt_thresh_{thresh_text}.nc'
                filename = f'{runid}.{daterange}.{season}.asia_precip_afi.ppt_thresh_{thresh_text}.nc'

            for mode in MODES:
                inputs[(runid, f'{mode}_of_precip_{season}')] = datadir / rel_path / filename

        output_path = (figsdir / 'AFI' /
                       f'{func.__name__}.{duration}.{season}.{domain}.{method}.ppt_thresh_{thresh_text}.pdf')
        super().__init__(func, inputs, [output_path], func_args=(season, domain, method))


def gen_task_ctrl():
    task_ctrl = TaskControl(__file__)

    season = 'jja'
    durations = ['short', 'long']
    precip_threshes = [0.1]
    methods = ['peak', 'harmonic']
    domains = ['china', 'asia']
    for duration, precip_thresh, domain in itertools.product(durations, precip_threshes, domains):
        task = AfiTask(fig_afi_mean, PATHS['datadir'], PATHS['figsdir'],
                       duration, precip_thresh, season, domain)
        task_ctrl.add(task)
        for method in methods:
            task = AfiTask(fig_afi_diurnal_cycle, PATHS['datadir'], PATHS['figsdir'],
                           duration, precip_thresh, season, domain, method)
            task_ctrl.add(task)

    return task_ctrl


if __name__ == '__main__':
    task_ctrl = gen_task_ctrl()
    task_ctrl.finalize().print_status()
    # task_ctrl.run()
