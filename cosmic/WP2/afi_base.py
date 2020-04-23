import sys
from pathlib import Path
import string

import iris
import matplotlib.pyplot as plt
import numpy as np

from cosmic.util import load_cmap_data


class AFI_basePlotter:
    MODES = ['amount', 'freq', 'intensity']

    TITLE_MODE_MAP = {
        'amount': 'amount',
        'freq': 'frequency',
        'intensity': 'intensity',
    }
    TITLE_RUNID_MAP = {
        'cmorph_8km': 'CMORPH',
        'al508': 'N1280',
        'ak543': 'N1280-EC',
    }

    def __init__(self, season, domain, method='peak'):
        self.season = season
        self.method = method
        assert domain in ['china', 'asia', 'europe']
        self.domain = domain
        if self.domain == 'china':
            self.fig = plt.figure(figsize=(10, 10))
        elif self.domain == 'asia':
            self.fig = plt.figure(figsize=(10, 8))
        elif self.domain == 'europe':
            self.fig = plt.figure(figsize=(10, 8))
        self.fig_axes, self.cb_axes = self.gen_axes()
        self.cubes = {}
        self.runids = list(self.TITLE_RUNID_MAP.keys())

    def set_cubes(self, cubes):
        self.cubes = cubes
        # for runid, cube_name in cubes.keys():
        #     if runid not in self.runids:
        #         self.runids.append(runid)

    def plot(self):
        print(f'plotting {self}')
        self.image_grid = []
        for i, runid in enumerate(self.runids):
            images = []
            for j, mode in enumerate(self.MODES):
                ax = self.fig_axes[i, j]
                images.append(self.plot_ax(ax, self.cubes[runid, f'{mode}_of_precip_{self.season}'], runid, mode))

                ax.coastlines(resolution='50m')
                if self.domain == 'china':
                    ax.set_xlim((97.5, 125))
                    ax.set_ylim((18, 41))
                    xticks = [100, 110, 120]
                    ax.set_xticks(xticks)
                    ax.set_xticks(np.linspace(98, 124, 14), minor=True)

                    yticks = [20, 30, 40]
                    ax.set_yticks(yticks)
                    ax.set_yticks(np.linspace(18, 40, 12), minor=True)
                    ax.set_xticklabels([f'${t}\\degree$ E' for t in xticks])
                    ax.set_yticklabels([f'${t}\\degree$ N' for t in yticks])
                elif self.domain == 'asia':
                    xticks = range(60, 160, 20)
                    ax.set_xticks(xticks)
                    ax.set_xticks(np.linspace(58, 150, 47), minor=True)

                    yticks = range(20, 60, 20)
                    ax.set_yticks(yticks)
                    ax.set_yticks(np.linspace(2, 56, 28), minor=True)
                    ax.set_xticklabels([f'${t}\\degree$ E' for t in xticks])
                    ax.set_yticklabels([f'${t}\\degree$ N' for t in yticks])
                elif self.domain == 'europe':
                    xticks = range(-20, 35, 10)
                    ax.set_xticks(xticks)
                    # ax.set_xticks(np.linspace(58, 150, 47), minor=True)

                    yticks = range(30, 70, 10)
                    ax.set_yticks(yticks)
                    # ax.set_yticks(np.linspace(2, 56, 28), minor=True)

                    xlabels = ([f'${abs(t)}\\degree$ W' for t in xticks if t < 0] +
                               [f'${t}\\degree$ E' for t in xticks if t >= 0])
                    ax.set_xticklabels(xlabels)
                    ax.set_yticklabels([f'${t}\\degree$ N' for t in yticks])


                ax.tick_params(labelbottom=True, labeltop=False, labelleft=True, labelright=False,
                               bottom=True, top=True, left=True, right=True, which='both')
                if i != 2:
                    ax.get_xaxis().set_ticklabels([])

                if j == 0:
                    ax.set_ylabel(self.TITLE_RUNID_MAP[runid])
                else:
                    ax.get_yaxis().set_ticklabels([])
                c = string.ascii_lowercase[i * len(self.runids) + j]
                ax.text(0.01, 1.04, f'({c})', size=12, transform=ax.transAxes)

            self.image_grid.append(images)

        self.add_titles_colourbars()

        self.fig.subplots_adjust(top=0.95, bottom=0.05, left=0.07, right=0.99, wspace=0.1, hspace=0.1)

    def save(self, path):
        plt.savefig(path)
        plt.close('all')
