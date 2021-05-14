import sys
import multiprocessing
import gdal
from osgeo import osr
import pandas as pd
import numpy as np
from pmdarima.arima import auto_arima
import warnings
import sys

warnings.filterwarnings("ignore")


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


def crossCorrelation(array):
    limit = int(array.shape[0]/2)
    ind = array[:limit]
    dep = array[limit:]
    nans = np.isnan(ind) | np.isnan(dep)
    ind = ind[~nans]
    dep = dep[~nans]
    try:
        saved = auto_arima(ind, start_p=0, start_q=0, n_fits=50)
        order_i = saved.order[1]
        x_new = saved.resid()
        y_new = saved.fit(dep).resid()
        df = pd.DataFrame(data={'spei': x_new, 'svi': y_new})
        sign, cc = [], []
        for n in np.arange(0, 20, 1):
            dfc = df.copy()
            dfc['spei{}'.format(n)] = dfc['spei'].shift(n)
            dfsub = dfc[['svi', 'spei{}'.format(n)]]
            dfsub.dropna(how='any', inplace=True)
            correlation = np.corrcoef(dfsub['svi'], dfsub['spei{}'.format(n)])
            cc.append(correlation[0][1])
            sign.append(np.abs(correlation[0][1]) >
                        2/(len(dfc['svi']) - np.abs(n))**0.5)
        ix, corr = np.argmax(np.array(cc)), np.max(np.array(cc))
        sig = sign[np.argmax(np.array(cc))]
        return order_i, ix, corr, sig
    except (ValueError, np.linalg.LinAlgError):
        order_i, ix, corr, sig = np.nan, np.nan, np.nan, np.nan
        return order_i, ix, corr, sig


def unpacking_apply_along_axis(chunksss):
    return np.apply_along_axis(chunksss[0], chunksss[1], chunksss[2])


def parallel_apply_along_axis(func1d, axis, arr):
    """
    Like numpy.apply_along_axis(), but takes advantage of multiple
    cores.
    """
    # Effective axis where apply_along_axis() will be applied by each
    # worker (any non-zero axis number would work, so as to allow the use
    # of `np.array_split()`, which is only done on axis 0):
    effective_axis = 1 if axis == 0 else axis
    if effective_axis != axis:
        arr = arr.swapaxes(axis, effective_axis).swapaxes(effective_axis,
                                                          effective_axis+1)

    # Chunks for the mapping (only a few chunks):
    chunks = [(func1d, effective_axis+1, sub_arr)
              for sub_arr in np.array_split(arr, multiprocessing.cpu_count())]

    pool = multiprocessing.Pool()
    individual_results = pool.map(unpacking_apply_along_axis, chunks)
    # Freeing the workers:
    pool.close()
    pool.join()
    merged = np.concatenate(individual_results)
    return merged


raster = str(sys.argv[1])
print(raster)
data = gdal.Open(raster)
data_array = data.ReadAsArray()

results = parallel_apply_along_axis(crossCorrelation, 0, data_array)
save_raster(raster, results[:, :, 0], '{}_int.tif'.format(raster[:-4]))
save_raster(raster, results[:, :, 1], '{}_lag.tif'.format(raster[:-4]))
save_raster(raster, results[:, :, 2], '{}_corr.tif'.format(raster[:-4]))
save_raster(raster, results[:, :, 3], '{}_sig.tif'.format(raster[:-4]))
