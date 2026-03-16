import attrs


@attrs.frozen
class FujifilmRecipeData:
    film_simulation: str
    dynamic_range: str
    d_range_priority: str
    grain_roughness: str
    grain_size: str
    color_chrome_effect: str
    color_chrome_fx_blue: str
    white_balance: str
    white_balance_red: int
    white_balance_blue: int
    highlight: str
    shadow: str
    color: str
    sharpness: str
    high_iso_nr: str
    clarity: str
    monochromatic_color_warm_cool: str
    monochromatic_color_magenta_green: str
    name: str = ""


@attrs.frozen
class ImageExifData:
    # Standard (non-FujiFilm group) fields
    camera_make: str = ""
    camera_model: str = ""
    iso: str = ""
    exposure_compensation: str = ""
    date_taken: str = ""
    aperture: str = ""
    shutter_speed: str = ""
    focal_length: str = ""

    # Shooting settings (FujiFilm group, stored on Image)
    quality: str = ""
    flash_mode: str = ""
    flash_exposure_comp: str = ""
    focus_mode: str = ""
    shutter_type: str = ""
    lens_modulation_optimizer: str = ""
    picture_mode: str = ""
    drive_mode: str = ""
    image_stabilization: str = ""

    # Creative / recipe settings (FujiFilm group, stored on FujifilmExif)
    film_simulation: str = ""
    dynamic_range: str = ""
    dynamic_range_setting: str = ""
    development_dynamic_range: str = ""
    white_balance: str = ""
    white_balance_fine_tune: str = ""
    color_temperature: str = ""
    highlight_tone: str = ""
    shadow_tone: str = ""
    color: str = ""
    sharpness: str = ""
    noise_reduction: str = ""
    clarity: str = ""
    color_chrome_effect: str = ""
    color_chrome_fx_blue: str = ""
    grain_effect_roughness: str = ""
    grain_effect_size: str = ""
    bw_adjustment: str = ""
    bw_magenta_green: str = ""
    d_range_priority: str = ""
    d_range_priority_auto: str = ""
    auto_dynamic_range: str = ""

    # Autofocus settings (FujiFilm group, stored on FujifilmExif)
    af_mode: str = ""
    focus_pixel: str = ""
    af_s_priority: str = ""
    af_c_priority: str = ""
    focus_mode_2: str = ""
    pre_af: str = ""
    af_area_mode: str = ""
    af_area_point_size: str = ""
    af_area_zone_size: str = ""
    af_c_setting: str = ""
    af_c_tracking_sensitivity: str = ""
    af_c_speed_tracking_sensitivity: str = ""
    af_c_zone_area_switching: str = ""

    # Drive / flash / stabilization (FujiFilm group, stored on FujifilmExif)
    slow_sync: str = ""
    auto_bracketing: str = ""
    drive_speed: str = ""
    crop_mode: str = ""
    flicker_reduction: str = ""

    # Shot metadata (FujiFilm group, stored on FujifilmExif)
    sequence_number: str = ""
    exposure_count: str = ""
    image_generation: str = ""
    image_count: str = ""
    scene_recognition: str = ""

    # Warnings / status (FujiFilm group, stored on FujifilmExif)
    blur_warning: str = ""
    focus_warning: str = ""
    exposure_warning: str = ""

    # Lens info (FujiFilm group, stored on FujifilmExif)
    min_focal_length: str = ""
    max_focal_length: str = ""
    max_aperture_at_min_focal: str = ""
    max_aperture_at_max_focal: str = ""

    # Camera hardware info (FujiFilm group, stored on FujifilmExif)
    version: str = ""
    internal_serial_number: str = ""
    fuji_model: str = ""
    fuji_model_2: str = ""

    # Face detection (FujiFilm group, stored on FujifilmExif)
    faces_detected: str = ""
    num_face_elements: str = ""
    face_element_positions: str = ""
    face_element_selected: str = ""
    face_element_types: str = ""
    face_positions: str = ""
