import datetime as dt
from pathlib import Path

import iris
from matplotlib.colors import LogNorm
import matplotlib.pyplot as plt
import numpy as np

from cosmic.util import load_cmap_data

aphrodite_dir = Path('aphrodite_data/025deg')


def plot_aphrodite_seasonal_analysis(datadir, figsdir):
    ppt = iris.load_cube(str(datadir / aphrodite_dir / 'APHRO_MA_025deg_V1901.2009.nc'),
                         ' daily precipitation analysis interpolated onto 0.25deg grids')
    epoch2009 = dt.datetime(2009, 1, 1)
    time_index = np.array([epoch2009 + dt.timedelta(minutes=m) for m in ppt.coord('time').points])
    jja = ((time_index >= dt.datetime(2009, 6, 1)) & (time_index < dt.datetime(2009, 9, 1)))
    ppt_jja = ppt[jja]
    ppt_jja_mean = ppt_jja.data.mean(axis=0)

    fig = plt.figure('aphrodite2009 JJA')
    plt.clf()

    lon_min, lon_max = ppt.coord('longitude').points[[0, -1]]
    lat_min, lat_max = ppt.coord('latitude').points[[0, -1]]

    extent = (lon_min, lon_max, lat_min, lat_max)

    if True:
        cmap, norm, bounds, cbar_kwargs = load_cmap_data('cmap_data/li2018_fig2_cb1.pkl')

        im = plt.imshow(ppt_jja_mean, origin='lower', extent=extent, cmap=cmap, norm=norm)
        plt.colorbar(im, label=f'amount precip. (mm day$^{{-1}}$)',
                     orientation='horizontal', **cbar_kwargs, spacing='uniform')
    else:
        im = plt.imshow(ppt_jja_mean, origin='lower', extent=extent, norm=LogNorm())
        plt.colorbar(im, label=f'amount precip. (mm day$^{{-1}}$)',
                     orientation='horizontal' )
    fig.set_size_inches(12, 8)
    ax = plt.gca()
    ax.set_xlim((57, 150))
    ax.set_ylim((1, 56))
    figsdir.mkdir(exist_ok=True, parents=True)
    plt.savefig(figsdir / 'asia_aphrodite_2009_jja.png')

    ax.set_xlim((97.5, 125))
    ax.set_ylim((18, 41))
    ax.set_xticks([100, 110, 120])
    ax.set_yticks([20, 30, 40])
    fig.set_size_inches(6, 8)

    plt.savefig(figsdir / 'china_aphrodite_2009_jja.png')
