def classFactory(iface):
    from .geotiff_to_pmtiles_algorithm import PMTilesConverterPlugin
    return PMTilesConverterPlugin()