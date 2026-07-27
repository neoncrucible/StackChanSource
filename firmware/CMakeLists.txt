# The following five lines of boilerplate have to be in your project's
# CMakeLists in this exact order for cmake to work correctly
cmake_minimum_required(VERSION 3.16)

set(PROJECT_VER "1.4.1-kade-eye.1")
add_definitions(-DFIRMWARE_VERSION=\"${PROJECT_VER}\")

# Materialise repository-safe custom images and audio before ESP-IDF scans
# the component asset directories.
execute_process(
    COMMAND python "${CMAKE_CURRENT_LIST_DIR}/custom_assets/prepare_assets.py"
    WORKING_DIRECTORY "${CMAKE_CURRENT_LIST_DIR}"
    RESULT_VARIABLE KADE_ASSET_RESULT
)
if(NOT KADE_ASSET_RESULT EQUAL 0)
    message(FATAL_ERROR "Failed to prepare Kade Eye assets")
endif()

# Add this line to disable the specific warning
add_compile_options(-Wno-missing-field-initializers)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(stack-chan)
