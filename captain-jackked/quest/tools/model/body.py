RESIDUAL_LEAN_MASS = 'residual_lean_mass'
MUSCULAR_LEAN_MASS = 'muscular_lean_mass'
FAT_MASS = 'fat_mass'

TISSUE_ENERGY_MAP = {
    RESIDUAL_LEAN_MASS: 41.0,
    MUSCULAR_LEAN_MASS: 13.0,
    FAT_MASS: 4.5
}

LETHARGIC = 'Lethargic'
SEDENTARY = 'Sedentary'
LIGHTLY_ACTIVE = '3-6 hrs/week'
MODERATELY_ACTIVE = '7-11 hrs/week'
VERY_ACTIVE = '12-18 hrs/week'
EXTREMELY_ACTIVE = '18+ hrs/week'

ACTIVITY_SCALING = 'activity_scaling'
PROTEIN_BMR_PERCENT = 'protein_bmr_percent'

ACTIVITY_DATA = {
    LETHARGIC: {
        ACTIVITY_SCALING: 1.15,
        PROTEIN_BMR_PERCENT: 0.15
    },
    SEDENTARY: {
        ACTIVITY_SCALING: 1.25,
        PROTEIN_BMR_PERCENT: 0.19
    },
    LIGHTLY_ACTIVE: {
        ACTIVITY_SCALING: 1.325,
        PROTEIN_BMR_PERCENT: 0.22
    },
    MODERATELY_ACTIVE: {
        ACTIVITY_SCALING: 1.4,
        PROTEIN_BMR_PERCENT: 0.26
    },
    VERY_ACTIVE: {
        ACTIVITY_SCALING: 1.45,
        PROTEIN_BMR_PERCENT: 0.29
    },
    EXTREMELY_ACTIVE: {
        ACTIVITY_SCALING: 1.5,
        PROTEIN_BMR_PERCENT: 0.33
    }
}

CALORIES_PER_GRAM_PROTEIN = 4.0
CALORIES_PER_GRAM_FAT = 9.0
CALORIES_PER_GRAM_CARBS = 4.0
MIN_FAT_PERCENT = 0.30

BMR = 'bmr'
MAINTENANCE = 'maintenance'
RECOMMENDED_PROTEIN = 'recommended_protein'
MIN_FAT = 'min_fat'
MAX_CARBS = 'max_carbs'


def _calc_residual_lean_mass(height_cm, is_male):
    factor = 6.3 if is_male else 5.67
    height_m = height_cm / 100.0
    return factor * (height_m ** 3)


def _calc_body_components(weight_kg, bf_pct, height_cm, is_male):
    fat_mass = weight_kg * (bf_pct / 100.0)
    lbm = weight_kg - fat_mass
    rlm = _calc_residual_lean_mass(height_cm, is_male)
    mlm = lbm - rlm
    return fat_mass, rlm, mlm


def _calc_age_factor(age):
    return 1.0 - (age - 25) / 300.0


def _calc_bmr(rlm, mlm, fat_mass, age):
    age_factor = _calc_age_factor(age)
    base_cost = (
        TISSUE_ENERGY_MAP[RESIDUAL_LEAN_MASS] * rlm + 
        TISSUE_ENERGY_MAP[MUSCULAR_LEAN_MASS] * mlm + 
        TISSUE_ENERGY_MAP[FAT_MASS] * fat_mass
    )
    return base_cost * age_factor


def _calc_maintenance(bmr, activity_level):
    data = ACTIVITY_DATA.get(activity_level, ACTIVITY_DATA[SEDENTARY])
    return bmr * data[ACTIVITY_SCALING]


def _calc_macros(bmr, maintenance, activity_level):
    data = ACTIVITY_DATA.get(activity_level, ACTIVITY_DATA[SEDENTARY])
    protein_g = (bmr * data[PROTEIN_BMR_PERCENT]) / CALORIES_PER_GRAM_PROTEIN
    fat_g = (bmr * MIN_FAT_PERCENT) / CALORIES_PER_GRAM_FAT
    carbs_g = (maintenance - (protein_g * CALORIES_PER_GRAM_PROTEIN + fat_g * CALORIES_PER_GRAM_FAT)) / CALORIES_PER_GRAM_CARBS
    return protein_g, fat_g, carbs_g


def calculate_bf_percent(is_male, height, waist, neck, hip=0):
    if height < 0 or waist < 0 or neck < 0 or hip < 0:
        return None
    
    slope, intercept = (143, -21.7) if is_male else (91, -49.5)
    
    if is_male:
        indep_x = (waist - neck) / height
    else:
        indep_x = (waist + hip - neck) / height
        
    return (slope * indep_x) + intercept


def calc_bmi(weight_kg, height_cm):
    if height_cm <= 0:
        return 0.0
    return weight_kg / ((height_cm / 100.0) ** 2)


def calc_ffm(weight_kg, bf_pct):
    return weight_kg * (1.0 - bf_pct / 100.0)


def calc_ffmi(ffm, height_cm):
    if height_cm <= 0:
        return 0.0
    return ffm / ((height_cm / 100.0) ** 2)


def calc_adj_ffmi(ffmi, height_cm):
    if height_cm <= 0:
        return 0.0
    return ffmi + 6.1 * (1.8 - height_cm / 100.0)


def compute_macros(is_male, age, height_cm, weight_kg, bf_pct, activity_level):
    if height_cm <= 0 or weight_kg <= 0:
        return None

    fat_mass, rlm, mlm = _calc_body_components(weight_kg, bf_pct, height_cm, is_male)
    bmr = _calc_bmr(rlm, mlm, fat_mass, age)
    maintenance = _calc_maintenance(bmr, activity_level)
    protein, fat, carbs = _calc_macros(bmr, maintenance, activity_level)
    
    return {
        BMR: bmr,
        MAINTENANCE: maintenance,
        RECOMMENDED_PROTEIN: protein,
        MIN_FAT: fat,
        MAX_CARBS: carbs
    }
