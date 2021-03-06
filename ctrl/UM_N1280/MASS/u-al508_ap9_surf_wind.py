import sys
sys.path.insert(0, '.')
from common import AP9_SURF_WIND, BASE_OUTPUT_DIRPATH

AP9_SURF_WIND['start_year_month'] = (2006, 6)
AP9_SURF_WIND['end_year_month'] = (2006, 8)

ACTIVE_RUNIDS = ['u-al508']

MASS_INFO = {}
MASS_INFO['u-al508'] = {
    'stream': {
        'ap9': AP9_SURF_WIND,
    },
}
