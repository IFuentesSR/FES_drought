import sys
import multiprocessing
import gdal
from osgeo import osr
import pandas as pd
import numpy as np
from pmdarima.arima import auto_arima
import warnings

# warnings.filterwarnings("ignore")


def save_raster(input, array, output_file):
    """Short summary.

    Parameters
    ----------
    input : str
        Description of parameter `input`.
    array : np.array
        Description of parameter `array`.
    output_file : str
        Description of parameter `output_file`.

    Returns
    -------
    type
        Description of returned object.

    """

    raster = gdal.Open(input)
    geo = raster.GetGeoTransform()
    wkt = raster.GetProjection()
    band = raster.GetRasterBand(1)
    driver = gdal.GetDriverByName("GTiff")

    dst_ds = driver.Create(output_file,
                           band.XSize,
                           band.YSize,
                           1,
                           gdal.GDT_Float32)

    #  writting output raster
    dst_ds.GetRasterBand(1).WriteArray(array)
    #  setting nodata value
    dst_ds.GetRasterBand(1).SetNoDataValue(-999)
    #  setting extension of output raster
    #  top left x, w-e pixel resolution, rotation, top left y, rotation, n-s pixel resolution
    dst_ds.SetGeoTransform(geo)
    # setting spatial reference of output raster
    srs = osr.SpatialReference()
    srs.ImportFromWkt(wkt)
    dst_ds.SetProjection(srs.ExportToWkt())
    #  Close output raster dataset

    dst_ds = None
    

def cc(x, y, maxlags):
    correls = np.correlate(x, y, mode='full')
    correls /= np.sqrt(np.dot(x, x) * np.dot(y, y))
    lags = np.arange(-maxlags, maxlags + 1)
    correls = correls[len(x) - 1 - maxlags:len(x) + maxlags]
    return correls, lags


def crossCorrelation(array):
    limit = int(array.shape[0]/2)
    ind = array[:limit]
    dep = array[limit:]
    nans = np.isnull(ind) | np.isnull(dep)
    ind = ind[~nans]
    dep = dep[~nans]
    if len(dep) == 0:
        order_i, ix, corr = -999, -999, -999
        return order_i, ix, corr, 0
    else:
        try:
            saved = auto_arima(ind, start_p=0, start_q=0, n_fits=50)
            order_i = saved.order[1]
            x_new = saved.resid()
            y_new = saved.fit(dep).resid()
            df = pd.DataFrame(data={'spei': x_new, 'svi': y_new})
            corrs, lgs = cc(df['spei'], df['svi'], 48)
            corrs, lgs = corrs[48:], lgs[48:]
            ix_corr = np.argmax(corrs)
            corr = corrs[ix_corr]
            ix = lgs[ix_corr]
            sig = np.abs(corr) > 2/(len(df['svi']) - np.abs(ix))**0.5
            return order_i, ix, corr, int(sig)
        except (ValueError, np.linalg.LinAlgError):
            order_i, ix, corr, sig = -999, -999, -999, 0
            return order_i, ix, corr, int(sig)

