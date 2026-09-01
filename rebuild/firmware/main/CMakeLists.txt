idf_component_register(
    SRCS "probe7.cpp"
    INCLUDE_DIRS "."
    PRIV_REQUIRES esp_app_format esp_driver_i2c esp_driver_i2s esp_timer esp_codec_dev
)
