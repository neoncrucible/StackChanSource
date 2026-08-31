idf_component_register(
    SRCS "probe3.cpp"
    INCLUDE_DIRS "."
    PRIV_REQUIRES esp_app_format esp_driver_i2c esp_timer
)
