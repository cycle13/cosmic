import datetime as dt

import iris
from iris.experimental import equalise_cubes
import numpy as np

from remake import TaskControl, Task, remake_task_control

from cosmic.config import PATHS, CONSTRAINT_ASIA
from cosmic.datasets.aphrodite import ALL_YEARS, FILE_TPL


def combine_years(inputs, outputs):
    constraint_name = iris.Constraint(name=' daily precipitation analysis interpolated onto 0.25deg grids')
    cubes = []
    # Each cube has its own time coords starting with that cube's year,
    # e.g.units = Unit('minutes since 1998-01-01 00:00', calendar='gregorian')
    # Normalize them to all use the first one.
    for year, inputpath in zip(ALL_YEARS, inputs):
        cube = iris.load_cube(str(inputpath), constraint=(CONSTRAINT_ASIA & constraint_name))
        if year == ALL_YEARS[0]:
            start_year = dt.datetime(year, 1, 1)
            time_coord = cube.coord('time')
        else:
            curr_year = dt.datetime(year, 1, 1)
            diff_in_minutes = (curr_year - start_year).total_seconds() / 60
            cube.coord('time').units = time_coord.units
            cube.coord('time').points = np.array([p + diff_in_minutes for p in cube.coord('time').points])
        cubes.append(cube)

    cubes = iris.cube.CubeList(cubes)
    equalise_cubes.equalise_attributes(cubes)
    cube = cubes.concatenate_cube()

    dates = [start_year + dt.timedelta(minutes=p) for p in cube.coord('time').points]
    jja = [d.month in [6, 7, 8] for d in dates]

    # Convert from mm to mm hr-1.
    # N.B. orig units are mm, but this is really mm day-1 as each timeslice is one day.
    assert cube.units == 'mm'
    cube.units = 'mm hr-1'
    cube.data /= 24
    iris.save(cube, str(outputs[0]))
    cube_jja = cube[jja]
    precip_flux_mean = cube_jja.collapsed('time', iris.analysis.MEAN)
    precip_flux_mean.rename('precip_flux_mean')

    iris.save(iris.cube.CubeList([cube_jja, precip_flux_mean]), str(outputs[1]))


@remake_task_control
def gen_task_ctrl():
    tc = TaskControl(__file__)
    datadir = PATHS['datadir'] / 'aphrodite_data/025deg'
    filenames = [datadir / FILE_TPL.format(year=year) for year in ALL_YEARS]
    tc.add(Task(combine_years, filenames, [datadir / 'aphrodite_combined_all.nc', datadir / 'aphrodite_combined_jja.nc']))

    return tc
