import itertools
from pathlib import Path

SCRIPT_PATH = 'cmorph_extract_europe_8km_30min.py'

BASEDIR = Path('/gws/nopw/j04/cosmic/mmuetz/data/cmorph_data/8km-30min')

years = range(1999, 2019)
months = range(6, 9)
years_months = list(itertools.product(years, months))

CONFIG_KEYS = [f'{y}{m:02}' for y, m in years_months]

BSUB_KWARGS = {
    'job_name': 'cmorph_eeu',
    'queue': 'short-serial',
    'max_runtime': '03:00',
    'mem': 32000,
}

SCRIPT_ARGS = {}
for key, (year, month) in zip(CONFIG_KEYS, years_months):
    SCRIPT_ARGS[key] = (year, month)
