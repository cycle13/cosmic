from pathlib import Path

from cosmic.config import PATHS

orog_path = PATHS['gcosmic'] / 'share' / 'ancils' / 'N1280' / 'qrparm.orog'
land_sea_mask = PATHS['gcosmic'] / 'share' / 'ancils' / 'N1280' / 'qrparm.landfrac'

cache_key_tpl = (PATHS['datadir'] / 'orog_precip' / 'experiments' / 'cache' /
                 'cache_mask.N1280.dist_{dist_thresh}.circ_True.npy')

surf_wind_path_tpl = (PATHS['datadir'] / 'u-al508' / 'ap9.pp' /
                      'surface_wind_{year}{month:02}' /
                      'al508a.p9{year}{month:02}.asia.nc')

orog_mask_path_tpl = (PATHS['datadir'] / 'orog_precip' / 'experiments' /
                      'u-al508_direct_orog_mask.dp_{dotprod_thresh}.dist_{dist_thresh}.{year}{month:02}.asia.nc')

precip_path_tpl = (PATHS['datadir'] / 'u-al508' / 'ap9.pp' /
                   'precip_{year}{month:02}' /
                   'al508a.p9{year}{month:02}.asia_precip.nc')

orog_precip_path_tpl = (PATHS['datadir'] / 'orog_precip' / 'experiments' /
                        'u-al508_direct_orog.dp_{dotprod_thresh}.dist_{dist_thresh}.{year}{month:02}.asia.nc')

orog_precip_fig_tpl = (PATHS['datadir'] / 'orog_precip' / 'experiments' / 'figs' /
                       'u-al508_direct_orog.dp_{dotprod_thresh}.dist_{dist_thresh}.{year}{season}.asia.{precip_type}.png')



def fmtp(path: Path, *args, **kwargs) -> Path:
    return Path(str(path).format(*args, **kwargs))
