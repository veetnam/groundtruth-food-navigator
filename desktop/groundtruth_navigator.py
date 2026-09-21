#!/usr/bin/env python3
"""
GroundTruth — the Household Food Navigator (offline desktop demo, v4)
------------------------------------------------------
Built for households enrolled in FDPIR (the Food Distribution
Program on Indian Reservations) who are managing food and money
decisions on a reservation — or, in Oklahoma, without one, since
FDPIR eligibility there does not require reservation residency
(see the About page).

Four sections from the main menu: Calculator (a step wizard),
Recipes, Locator, and About.

Runs fully offline. No network calls, no server, no accounts. Data
you enter (household size, income, expenses, ZIP code) is held in
memory only, shared between sections while the app is open, and is
gone the moment you close it — nothing is written to disk.

HACKATHON DEMO NOTE ON DATA:
  - FOOD_PACKAGES: illustrative food lists. Replace with an agency's
    actual current monthly list before a real submission.
  - Per-item macros/unit_cost: representative, not agency-specific
    pricing.
  - FDPIR_SITES: real town names and approximate coordinates, but
    placeholder street addresses/phone numbers — replace with a real
    directory before a live demo.
  - ZIP_COORDINATES: a small hand-picked sample, not a real ZIP
    centroid table.
  - Statistics on the About page are sourced to USDA/HHS publications
    current as of this build; verify against fna.usda.gov and
    aspe.hhs.gov before citing them in anything beyond a demo, since
    poverty guidelines and program figures update annually.

Run with:  python3 fdpir_navigator_v4.py
(Needs python3-tk on Linux: sudo apt install python3-tk)
"""

from __future__ import annotations

import json
import math
import traceback
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ===========================================================================
# DATA LAYER
# ===========================================================================

@dataclass(frozen=True)
class FoodItem:
    unit: str
    servings_per_unit: int
    kcal: int
    protein_g: int
    carbs_g: int
    fat_g: int
    sodium_mg: int
    added_sugar_g: int
    category: str
    unit_cost: float
    meal_ready: bool = True

    @property
    def cost_per_serving(self) -> float:
        return self.unit_cost / self.servings_per_unit


FOOD_ITEMS: Dict[str, FoodItem] = {
    "Canned chicken":          FoodItem("12oz can",    3,  70, 13, 0,  2, 270,  0, "protein", 2.50),
    "Frozen ground beef":      FoodItem("1 lb",         4, 280, 19, 0, 22,  75,  0, "protein", 4.50),
    "Canned salmon":           FoodItem("14.75oz can",  3, 150, 20, 0,  7, 380,  0, "protein", 3.50),
    "Peanut butter":           FoodItem("18oz jar",    27, 190,  8, 7, 16, 140,  3, "protein", 3.00),
    "Pinto beans (dry)":       FoodItem("1 lb bag",    12, 160, 10, 30, 1,   5,  1, "protein", 1.50),
    "Eggs (shelf-stable)":     FoodItem("dozen",       12,  70,  6, 0,  5,  65,  0, "protein", 3.00),
    "Whole wheat flour":       FoodItem("5 lb bag",    75, 100,  4, 22, 0,   0,  0, "grain",   3.50, meal_ready=False),
    "Brown rice":              FoodItem("2 lb bag",    20, 160,  4, 34, 1,   5,  0, "grain",   2.50),
    "Oats":                    FoodItem("42oz box",    30, 150,  5, 27, 3,   0,  1, "grain",   3.50),
    "Corn flakes cereal":      FoodItem("18oz box",    18, 100,  2, 24, 0, 200,  3, "grain",   4.00, meal_ready=False),
    "Frozen mixed vegetables": FoodItem("2 lb bag",    11,  60,  2, 12, 0,  40,  3, "produce", 2.00),
    "Canned green beans":      FoodItem("14.5oz can",   4,  20,  1, 4,  0, 390,  1, "produce", 1.00),
    "Canned tomatoes":         FoodItem("14.5oz can",   4,  25,  1, 5,  0, 300,  3, "produce", 1.20),
    "Frozen fruit blend":      FoodItem("2 lb bag",     8,  90,  1, 22, 0,   5, 17, "produce", 3.50),
    "Canned peaches":          FoodItem("15oz can",     3, 100,  1, 24, 0,  10, 21, "produce", 1.80),
    "Shelf-stable milk":       FoodItem("1 qt",         4, 100,  8, 12, 2, 100, 12, "dairy",   1.50),
    "Cheese block":            FoodItem("2 lb",        32, 110,  7, 1,  9, 180,  0, "dairy",   6.00),
    "Vegetable oil":           FoodItem("48oz bottle", 96, 120,  0, 0, 14,   0,  0, "fat",     5.00),
    "Butter":                  FoodItem("1 lb",        32, 100,  0, 0, 11,  90,  0, "fat",     4.00),
}


@dataclass(frozen=True)
class FDPIRPackage:
    agency: str
    region: str
    source_note: str
    items: Dict[str, float]


# Seven illustrative agencies grouped by region. Oklahoma gets four because
# FDPIR eligibility there does not require living on a reservation (see
# About), so it's the region where this app matters to the widest group of
# households. Real tribe/agency names; illustrative food-package contents.
_DEFAULT_FOOD_PACKAGES: Dict[str, FDPIRPackage] = {
    "Navajo Nation FDPIR": FDPIRPackage(
        agency="Navajo Nation FDPIR", region="Southwest",
        source_note="Illustrative — replace with the agency's current published monthly list.",
        items={
            "Canned chicken": 2, "Frozen ground beef": 2, "Peanut butter": 1,
            "Pinto beans (dry)": 2, "Eggs (shelf-stable)": 1, "Whole wheat flour": 1,
            "Brown rice": 1, "Oats": 1, "Frozen mixed vegetables": 2,
            "Canned green beans": 3, "Canned tomatoes": 2, "Frozen fruit blend": 1,
            "Canned peaches": 2, "Shelf-stable milk": 4, "Cheese block": 1, "Vegetable oil": 1,
        },
    ),
    "Oglala Sioux FDPIR": FDPIRPackage(
        agency="Oglala Sioux FDPIR", region="Great Plains",
        source_note="Illustrative — replace with the agency's current published monthly list.",
        items={
            "Canned salmon": 2, "Frozen ground beef": 1, "Peanut butter": 2,
            "Pinto beans (dry)": 1, "Eggs (shelf-stable)": 1, "Brown rice": 2,
            "Corn flakes cereal": 1, "Frozen mixed vegetables": 1,
            "Canned green beans": 2, "Canned tomatoes": 1, "Canned peaches": 2,
            "Shelf-stable milk": 4, "Cheese block": 1, "Butter": 1,
        },
    ),
    "Choctaw Nation FDPIR": FDPIRPackage(
        agency="Choctaw Nation FDPIR", region="Oklahoma",
        source_note="Illustrative — replace with the Choctaw Nation's current published monthly list.",
        items={
            "Canned chicken": 2, "Peanut butter": 1, "Pinto beans (dry)": 2,
            "Brown rice": 2, "Oats": 1, "Frozen mixed vegetables": 2,
            "Canned tomatoes": 2, "Canned peaches": 2, "Shelf-stable milk": 4,
            "Cheese block": 1, "Vegetable oil": 1,
        },
    ),
    "Cherokee Nation FDPIR": FDPIRPackage(
        agency="Cherokee Nation FDPIR", region="Oklahoma",
        source_note="Illustrative — replace with the Cherokee Nation's current published monthly list.",
        items={
            "Frozen ground beef": 2, "Canned salmon": 1, "Peanut butter": 1,
            "Pinto beans (dry)": 1, "Eggs (shelf-stable)": 1, "Brown rice": 1,
            "Corn flakes cereal": 1, "Frozen mixed vegetables": 1, "Canned green beans": 2,
            "Frozen fruit blend": 1, "Shelf-stable milk": 4, "Cheese block": 1, "Butter": 1,
        },
    ),
    "Chickasaw Nation FDPIR": FDPIRPackage(
        agency="Chickasaw Nation FDPIR", region="Oklahoma",
        source_note="Illustrative — replace with the Chickasaw Nation's current published monthly list.",
        items={
            "Canned chicken": 1, "Canned salmon": 1, "Peanut butter": 2,
            "Pinto beans (dry)": 1, "Whole wheat flour": 1, "Brown rice": 1,
            "Frozen mixed vegetables": 1, "Canned tomatoes": 1, "Canned peaches": 1,
            "Frozen fruit blend": 1, "Shelf-stable milk": 3, "Cheese block": 1, "Vegetable oil": 1,
        },
    ),
    "Muscogee (Creek) Nation FDPIR": FDPIRPackage(
        agency="Muscogee (Creek) Nation FDPIR", region="Oklahoma",
        source_note="Illustrative — replace with the Muscogee (Creek) Nation's current published monthly list.",
        items={
            "Frozen ground beef": 1, "Canned chicken": 1, "Peanut butter": 1,
            "Pinto beans (dry)": 2, "Eggs (shelf-stable)": 1, "Oats": 1,
            "Corn flakes cereal": 1, "Frozen mixed vegetables": 2, "Canned green beans": 1,
            "Canned tomatoes": 1, "Canned peaches": 1, "Shelf-stable milk": 3, "Butter": 1,
            "Vegetable oil": 1,
        },
    ),
    "State-administered FDPIR (example)": FDPIRPackage(
        agency="State-administered FDPIR (example)", region="Other",
        source_note="Illustrative — replace with the agency's current published monthly list.",
        items={
            "Canned chicken": 1, "Canned salmon": 1, "Peanut butter": 1,
            "Pinto beans (dry)": 1, "Whole wheat flour": 1, "Oats": 1,
            "Corn flakes cereal": 1, "Frozen mixed vegetables": 2,
            "Canned tomatoes": 2, "Frozen fruit blend": 1, "Shelf-stable milk": 3,
            "Cheese block": 1, "Vegetable oil": 1,
        },
    ),
}

AGENCY_DATA_FILENAME = "food_packages.json"


def load_food_packages() -> Dict[str, FDPIRPackage]:
    """Start from the bundled illustrative packages, then look for a
    food_packages.json file next to this script and let it add or override
    agencies — this is the real path to production data: a caseworker or
    admin updates one JSON file monthly, no code changes needed.

    Expected format:
      {
        "Some Agency FDPIR": {
          "region": "Oklahoma",
          "source_note": "Effective March 2027, per agency office.",
          "items": {"Canned chicken": 2, "Brown rice": 1}
        }
      }
    Item names must already exist in FOOD_ITEMS (this loader assigns
    quantities of known items; it doesn't define new items' nutrition/cost).
    Any problem reading the file — missing, malformed, wrong types — is
    handled by silently keeping the bundled defaults, since this always
    runs before any UI exists to show an error dialog.
    """
    packages = dict(_DEFAULT_FOOD_PACKAGES)
    try:
        external_path = Path(__file__).resolve().parent / AGENCY_DATA_FILENAME
    except NameError:
        return packages  # no __file__ (e.g. run in some embedded contexts)

    if not external_path.is_file():
        return packages

    try:
        with open(external_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return packages
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return packages

    for agency_name, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        raw_items = entry.get("items", {})
        if not isinstance(raw_items, dict):
            continue
        items: Dict[str, float] = {}
        for item_name, qty in raw_items.items():
            if item_name in FOOD_ITEMS and isinstance(qty, (int, float)) and qty > 0:
                items[item_name] = float(qty)
        if items:
            packages[str(agency_name)] = FDPIRPackage(
                agency=str(agency_name),
                region=str(entry.get("region", "Other")),
                source_note=str(entry.get("source_note", f"Loaded from {AGENCY_DATA_FILENAME}.")),
                items=items,
            )
    return packages


FOOD_PACKAGES: Dict[str, FDPIRPackage] = load_food_packages()

_PREFERRED_REGION_ORDER = ["Southwest", "Great Plains", "Oklahoma", "Other"]
_present_regions = {pkg.region for pkg in FOOD_PACKAGES.values()}
AGENCY_REGIONS: List[str] = ([r for r in _PREFERRED_REGION_ORDER if r in _present_regions] +
                             sorted(_present_regions - set(_PREFERRED_REGION_ORDER)))

DAILY_SODIUM_GUIDELINE_MG_PER_PERSON = 2300
DAILY_ADDED_SUGAR_GUIDELINE_G_PER_PERSON = 50
DAYS_PER_MONTH = 30
WEEKS_PER_MONTH = DAYS_PER_MONTH / 7

EXPENSE_CATEGORIES = ["Housing (rent/mortgage)", "Utilities", "Transportation",
                      "Travel to distribution site", "Other essentials"]

# --- Locator: gas-cost assumptions (sourced, illustrative) ------------------
GAS_PRICE_PER_GALLON = 4.06   # U.S. DOT/BTS national average, August 2026
ASSUMED_MPG = 25               # illustrative average light-vehicle fuel economy


def estimate_monthly_gas_cost(round_trip_miles: float, trips_per_month: float) -> float:
    return trips_per_month * (round_trip_miles / ASSUMED_MPG) * GAS_PRICE_PER_GALLON


# --- School meals: 2026-2027 federal guidelines (sourced) -------------------
# HHS/ASPE 2026 poverty guidelines, 48 contiguous states: $15,960 for one
# person, +$5,680 per additional person. USDA sets NSLP free-meal eligibility
# at 130% of this and reduced-price at 185% (FNS, Income Eligibility
# Guidelines 2026-2027, effective July 1 2026 - June 30 2027).
FPL_BASE_1PERSON_ANNUAL = 15960
FPL_INCREMENT_PER_PERSON_ANNUAL = 5680
NSLP_FREE_MULTIPLIER = 1.30
NSLP_REDUCED_MULTIPLIER = 1.85


def nslp_income_thresholds_monthly(household_size: int) -> Tuple[float, float]:
    annual_fpl = FPL_BASE_1PERSON_ANNUAL + FPL_INCREMENT_PER_PERSON_ANNUAL * (household_size - 1)
    free_monthly = annual_fpl * NSLP_FREE_MULTIPLIER / 12
    reduced_monthly = annual_fpl * NSLP_REDUCED_MULTIPLIER / 12
    return free_monthly, reduced_monthly


# --- Recipes -----------------------------------------------------------------
@dataclass(frozen=True)
class RecipeIngredient:
    item_name: str
    servings_used: float


@dataclass(frozen=True)
class Recipe:
    name: str
    description: str
    ingredients: List[RecipeIngredient]
    steps: List[str]
    yields_servings: int
    allergens: List[str] = field(default_factory=list)
    best_for: List[str] = field(default_factory=list)


RECIPES: List[Recipe] = [
    Recipe(
        name="Chicken and Rice Skillet",
        description="A one-pan dinner built around canned chicken and rice.",
        ingredients=[RecipeIngredient("Canned chicken", 2), RecipeIngredient("Brown rice", 2),
                     RecipeIngredient("Frozen mixed vegetables", 1), RecipeIngredient("Vegetable oil", 1)],
        steps=[
            "Cook the rice according to the package directions.",
            "Warm the oil in a skillet over medium heat.",
            "Add the canned chicken and frozen vegetables and cook until heated through, about 5 minutes.",
            "Stir in the cooked rice and mix well.",
            "Season with whatever you have on hand and serve warm.",
        ],
        yields_servings=4, allergens=[], best_for=["Kid-friendly", "Dairy-free"],
    ),
    Recipe(
        name="Bean and Tomato Rice Bowl",
        description="A filling, meat-free bowl using pinto beans, rice, and tomatoes.",
        ingredients=[RecipeIngredient("Pinto beans (dry)", 2), RecipeIngredient("Brown rice", 2),
                     RecipeIngredient("Canned tomatoes", 2), RecipeIngredient("Vegetable oil", 1)],
        steps=[
            "Soak the dry pinto beans (overnight if possible), then simmer in fresh water until tender, 60-90 minutes.",
            "Cook the rice according to the package directions.",
            "Warm the oil in a saucepan, add the canned tomatoes, and simmer for 5 minutes.",
            "Stir the cooked beans into the tomatoes and simmer together for another 5 minutes.",
            "Serve the bean-and-tomato mixture over the rice.",
        ],
        yields_servings=4, allergens=[], best_for=["Vegetarian", "Dairy-free", "Kid-friendly"],
    ),
    Recipe(
        name="Salmon Vegetable Soup",
        description="A simple simmered soup that stretches canned salmon across a full pot.",
        ingredients=[RecipeIngredient("Canned salmon", 2), RecipeIngredient("Frozen mixed vegetables", 2),
                     RecipeIngredient("Canned tomatoes", 1), RecipeIngredient("Brown rice", 1)],
        steps=[
            "Bring a pot of water to a simmer and add the frozen vegetables and canned tomatoes.",
            "Simmer for 10 minutes, until the vegetables are tender.",
            "Stir in the rice and cook until done, about 20 minutes (add more water as needed).",
            "Flake in the canned salmon during the last 5 minutes, just to heat through.",
            "Season to taste and serve hot.",
        ],
        yields_servings=4, allergens=["Fish"], best_for=["Elder-friendly (soft texture)"],
    ),
    Recipe(
        name="Peanut Butter Oatmeal Breakfast",
        description="A quick, filling breakfast that uses shelf-stable pantry staples.",
        ingredients=[RecipeIngredient("Oats", 4), RecipeIngredient("Peanut butter", 2),
                     RecipeIngredient("Shelf-stable milk", 4), RecipeIngredient("Frozen fruit blend", 2)],
        steps=[
            "Bring the milk to a gentle simmer in a saucepan.",
            "Stir in the oats and cook, stirring occasionally, until thickened (about 5 minutes).",
            "Stir in the peanut butter until fully melted and combined.",
            "Top each bowl with the frozen fruit blend and serve.",
        ],
        yields_servings=4, allergens=["Peanuts", "Dairy"], best_for=["Kid-friendly"],
    ),
    Recipe(
        name="Cheesy Rice and Beans",
        description="A hearty, kid-friendly plate built from pantry basics.",
        ingredients=[RecipeIngredient("Brown rice", 2), RecipeIngredient("Pinto beans (dry)", 2),
                     RecipeIngredient("Cheese block", 4), RecipeIngredient("Canned green beans", 2)],
        steps=[
            "Cook the rice according to the package directions.",
            "Soak and simmer the pinto beans until tender (or substitute canned beans if you have them).",
            "Warm the canned green beans in a small saucepan.",
            "Combine the rice and beans in a serving dish and top with the cheese.",
            "Serve with the warmed green beans on the side.",
        ],
        yields_servings=4, allergens=["Dairy"], best_for=["Vegetarian", "Kid-friendly"],
    ),
    Recipe(
        name="Egg and Vegetable Scramble",
        description="A simple scramble that works for breakfast, lunch, or dinner.",
        ingredients=[RecipeIngredient("Eggs (shelf-stable)", 4), RecipeIngredient("Frozen mixed vegetables", 2),
                     RecipeIngredient("Cheese block", 2), RecipeIngredient("Vegetable oil", 1)],
        steps=[
            "Warm the oil in a skillet over medium heat.",
            "Add the frozen vegetables and cook until thawed and slightly softened, about 4 minutes.",
            "Beat the eggs and pour them into the skillet with the vegetables.",
            "Scramble gently until just set, then sprinkle cheese on top.",
            "Remove from heat once the cheese melts and serve.",
        ],
        yields_servings=4, allergens=["Eggs", "Dairy"], best_for=["Kid-friendly", "Elder-friendly (soft texture)"],
    ),
    Recipe(
        name="Dairy-Free Peach Oatmeal",
        description="A softer, dairy-free breakfast built around oats and canned peaches.",
        ingredients=[RecipeIngredient("Oats", 4), RecipeIngredient("Canned peaches", 3),
                     RecipeIngredient("Vegetable oil", 1)],
        steps=[
            "Cook the oats in water according to the package directions.",
            "Stir in a small spoon of oil for richness (optional).",
            "Top with canned peaches (and a little of their juice) and serve warm.",
        ],
        yields_servings=4, allergens=[], best_for=["Dairy-free", "Vegetarian", "Elder-friendly (soft texture)"],
    ),
    Recipe(
        name="Salmon and Green Bean Plate",
        description="A quick, low-carb plate for using up canned salmon and green beans.",
        ingredients=[RecipeIngredient("Canned salmon", 3), RecipeIngredient("Canned green beans", 3),
                     RecipeIngredient("Vegetable oil", 1)],
        steps=[
            "Warm the oil in a skillet over medium heat.",
            "Add the canned green beans and cook until heated through, about 3 minutes.",
            "Flake in the canned salmon and warm gently, stirring occasionally.",
            "Season to taste and serve.",
        ],
        yields_servings=4, allergens=["Fish"], best_for=["Low-carb", "Dairy-free"],
    ),
]

ALL_DIETARY_TAGS: List[str] = sorted({tag for r in RECIPES for tag in r.best_for})
ALL_ALLERGENS: List[str] = sorted({tag for r in RECIPES for tag in r.allergens})


@dataclass
class RecipeTotals:
    cost_total: float
    kcal_total: float
    protein_g_total: float
    carbs_g_total: float
    fat_g_total: float

    def per_serving(self, servings: int) -> Tuple[float, float, float, float, float]:
        return (self.cost_total / servings, self.kcal_total / servings, self.protein_g_total / servings,
                self.carbs_g_total / servings, self.fat_g_total / servings)


def compute_recipe_totals(recipe: Recipe) -> RecipeTotals:
    cost = kcal = protein = carbs = fat = 0.0
    for ing in recipe.ingredients:
        info = FOOD_ITEMS[ing.item_name]
        cost += ing.servings_used * info.cost_per_serving
        kcal += ing.servings_used * info.kcal
        protein += ing.servings_used * info.protein_g
        carbs += ing.servings_used * info.carbs_g
        fat += ing.servings_used * info.fat_g
    return RecipeTotals(cost_total=cost, kcal_total=kcal, protein_g_total=protein,
                         carbs_g_total=carbs, fat_g_total=fat)


def recipe_fits_package(recipe: Recipe, package: FDPIRPackage) -> bool:
    """A recipe 'fits' if the package has all its ingredients, or is missing
    at most one — a single swap is a normal kitchen substitution, not a
    reason to hide the recipe entirely. Requiring a perfect match turned out
    to zero out every recipe for some packages that were only missing one
    or two common items."""
    missing = sum(1 for ing in recipe.ingredients if ing.item_name not in package.items)
    return missing <= 1


def missing_ingredients(recipe: Recipe, package: FDPIRPackage) -> List[str]:
    """Which of a recipe's ingredients aren't in this package — shown on the
    card so 'fits' (allowing one substitution) never looks like a silent,
    unexplained gap."""
    return [ing.item_name for ing in recipe.ingredients if ing.item_name not in package.items]


# --- Locator -----------------------------------------------------------------
@dataclass(frozen=True)
class FDPIRSite:
    agency: str
    address: str
    phone: str
    hours: str
    lat: float
    lon: float


FDPIR_SITES: List[FDPIRSite] = [
    FDPIRSite("Navajo Nation FDPIR", "Example Distribution Center, Window Rock, AZ 86515 (placeholder address)",
              "(555) 555-0101", "Mon-Fri 8:00am-4:30pm (example hours)", 35.6805, -109.0523),
    FDPIRSite("Oglala Sioux FDPIR", "Example Distribution Center, Pine Ridge, SD 57770 (placeholder address)",
              "(555) 555-0102", "Mon-Fri 8:00am-4:30pm (example hours)", 43.0247, -102.5477),
    FDPIRSite("Choctaw Nation FDPIR", "Example Distribution Center, Durant, OK 74701 (placeholder address)",
              "(555) 555-0104", "Mon-Fri 8:00am-4:30pm (example hours)", 33.9943, -96.3708),
    FDPIRSite("Cherokee Nation FDPIR", "Example Distribution Center, Tahlequah, OK 74464 (placeholder address)",
              "(555) 555-0105", "Mon-Fri 8:00am-4:30pm (example hours)", 35.9151, -94.9702),
    FDPIRSite("Chickasaw Nation FDPIR", "Example Distribution Center, Ada, OK 74820 (placeholder address)",
              "(555) 555-0106", "Mon-Fri 8:00am-4:30pm (example hours)", 34.7745, -96.6783),
    FDPIRSite("Muscogee (Creek) Nation FDPIR", "Example Distribution Center, Okmulgee, OK 74447 (placeholder address)",
              "(555) 555-0107", "Mon-Fri 8:00am-4:30pm (example hours)", 35.6234, -95.9581),
    FDPIRSite("State-administered FDPIR (example)", "Example State FDPIR Office, Madison, WI 53703 (placeholder address)",
              "(555) 555-0103", "Mon-Fri 8:00am-4:30pm (example hours)", 43.0731, -89.4012),
]

# Real town names/approximate coordinates (public knowledge); a real build
# would bundle a full ZCTA centroid table for nationwide offline coverage.
ZIP_COORDINATES: Dict[str, Tuple[float, float]] = {
    "86515": (35.68, -109.05),   # Window Rock, AZ
    "87301": (35.53, -108.74),   # Gallup, NM
    "57770": (43.02, -102.55),   # Pine Ridge, SD
    "57701": (44.08, -103.23),   # Rapid City, SD
    "53703": (43.07, -89.38),    # Madison, WI
    "60601": (41.88, -87.63),    # Chicago, IL
    "74701": (33.99, -96.37),    # Durant, OK — Choctaw Nation
    "74464": (35.92, -94.97),    # Tahlequah, OK — Cherokee Nation
    "74820": (34.77, -96.68),    # Ada, OK — Chickasaw Nation
    "74447": (35.62, -95.96),    # Okmulgee, OK — Muscogee (Creek) Nation
    "73102": (35.47, -97.52),    # Oklahoma City, OK
    "74103": (36.15, -95.99),    # Tulsa, OK
    "73501": (34.60, -98.40),    # Lawton, OK
    "74501": (34.93, -95.77),    # McAlester, OK
}


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def find_nearest_sites(zip_code: str) -> Optional[List[Tuple[FDPIRSite, float]]]:
    coords = ZIP_COORDINATES.get(zip_code.strip())
    if coords is None:
        return None
    lat, lon = coords
    results = [(site, haversine_miles(lat, lon, site.lat, site.lon)) for site in FDPIR_SITES]
    return sorted(results, key=lambda pair: pair[1])


# --- About / education content, with sources --------------------------------
LEARN_SECTIONS = [
    (
        "What is FDPIR?",
        "The Food Distribution Program on Indian Reservations (FDPIR) provides USDA foods "
        "each month to income-eligible households living on a reservation, and to Native "
        "American households in approved areas near a reservation — or in Oklahoma. It's "
        "administered locally by a tribal organization or a state agency; foods offered "
        "change month to month.\nSource: USDA Food and Nutrition Service, fna.usda.gov/fdpir",
    ),
    (
        "Oklahoma is a specific exception",
        "Most of Oklahoma has no formal Indian reservations in the way other states do, "
        "following historical allotment policy. USDA's FDPIR eligibility rules explicitly "
        "account for this: an income-eligible household in Oklahoma with at least one member "
        "of a federally recognized tribe can qualify without living on a reservation at all — "
        "unlike most other states, where reservation residency (or a nearby approved area) is "
        "required.\nSource: USDA FNS FDPIR Factsheet (fna.usda.gov/fdpir/factsheet)",
    ),
    (
        "What is SNAP?",
        "The Supplemental Nutrition Assistance Program (SNAP) provides a monthly dollar "
        "benefit, loaded onto a card, spent on groceries at participating stores. The amount "
        "depends on household size, income, and expenses.",
    ),
    (
        "Why can't I have both?",
        "A household can be certified for FDPIR or SNAP, but not both in the same month — a "
        "federal program rule. Households often choose based on access — FDPIR doesn't "
        "require a nearby SNAP-accepting grocery store, since the food is distributed "
        "directly.",
    ),
    (
        "Food sovereignty — there may be more than FDPIR or SNAP",
        "Many tribal nations run their own food sovereignty programs — traditional food "
        "gardens, bison or fish programs, seed banks, and Indigenous-led nutrition "
        "initiatives — that go beyond what FDPIR or SNAP provide, and that can offer more "
        "cultural connection to food than USDA commodities alone. If your tribe runs one, it's "
        "worth asking your tribal government what's available alongside FDPIR or SNAP.\n"
        "Source: Administration for Children and Families, Tribal Food Sovereignty, Security, "
        "and Nutrition Guide (acf.gov/ana)",
    ),
    (
        "School meals — what to know",
        "Households currently enrolled in FDPIR or SNAP make their school-age children "
        "automatically eligible for free school meals through \"direct certification\" — no "
        "separate income application is required for that eligibility. For households not on "
        "either program, free meals are available at or below 130% of the federal poverty "
        "guideline, and reduced-price meals at or below 185%; the Calculator's Finances step "
        "shows both figures for your household size.\n"
        "Sources: USDA FNS Policy Memo FD-045 (Direct Certification for FDPIR households); "
        "USDA FNS Child Nutrition Income Eligibility Guidelines 2026-2027",
    ),
    (
        "How do I apply or switch?",
        "Contact your local FDPIR administering agency (for FDPIR) or your state/tribal SNAP "
        "office (for SNAP) directly — eligibility rules and documentation vary by agency and "
        "can change. This app doesn't submit applications or verify eligibility; it's a "
        "planning tool for once you know your numbers.",
    ),
    (
        "By the numbers",
        "• About 276 tribes currently receive FDPIR benefits, through roughly 100 tribal "
        "organizations and a small number of state agencies. (USDA FNS)\n"
        "• American Indian and Alaska Native households experienced food insecurity at "
        "23.3% from 2016-2021 — more than double the 11.1% rate across all U.S. households "
        "in the same period, the highest rate of any racial or ethnic group measured. "
        "(USDA Economic Research Service, EIB-269)\n"
        "• A commonly cited estimate is that roughly 1 in 4 American Indian and Alaska "
        "Native people experience food insecurity, a rate researchers link partly to distance "
        "from grocery stores, unemployment, and the history of federal land and food policy "
        "in Native communities. (National Library of Medicine; GAO-24-106218)",
    ),
    (
        "Data privacy",
        "This app runs entirely on your own computer. There is no account, no login, and no "
        "internet connection required or used — household size, program choice, income, "
        "expenses, and ZIP code never leave this device. Different sections of the app (the "
        "Calculator, Recipes, and Locator) can share information with each other only while "
        "the app is open, in memory — for example, a selected agency can filter Recipes, or a "
        "gas-cost estimate from Locator can be added to the Calculator's budget. None of it is "
        "written to disk, and all of it is gone the moment you close the app.",
    ),
    (
        "A note on data accuracy",
        "The FDPIR food packages, prices, recipes, and distribution site listings in this app "
        "are illustrative placeholders built to be structurally realistic, not verified current "
        "facts. Real FDPIR food packages change monthly or quarterly and vary by agency; real "
        "prices, gas costs, site addresses, and poverty guidelines change too, and are cited "
        "above as of this build — check fna.usda.gov and aspe.hhs.gov for current figures. "
        "Always confirm package contents, benefit amounts, and site information with your "
        "local administering agency before making a decision based on this app.",
    ),
]


# ===========================================================================
# CALCULATION LAYER
# ===========================================================================

def scale_factor(household_size: int) -> float:
    return max(household_size, 1) / 4.0


@dataclass
class FoodLine:
    item: str
    qty: float
    unit: str
    servings_total: float
    kcal_total: float
    protein_g_total: float
    carbs_g_total: float
    fat_g_total: float
    cost_total: float
    per_serving_kcal: int
    per_serving_protein: int
    per_serving_carbs: int
    per_serving_fat: int


@dataclass
class PackageTotals:
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    sodium_mg: float
    added_sugar_g: float
    produce_kcal_share_pct: float
    total_cost: float
    lines: List[FoodLine] = field(default_factory=list)


def totals_for_package(package: FDPIRPackage, household_size: int) -> PackageTotals:
    factor = scale_factor(household_size)
    total_kcal = total_protein = total_carbs = total_fat = 0.0
    total_sodium = total_sugar = total_cost = produce_kcal = 0.0
    lines: List[FoodLine] = []

    for item_name, monthly_qty in package.items.items():
        info = FOOD_ITEMS[item_name]
        scaled_qty = monthly_qty * factor
        servings_total = scaled_qty * info.servings_per_unit

        kcal = info.kcal * servings_total
        protein = info.protein_g * servings_total
        carbs = info.carbs_g * servings_total
        fat = info.fat_g * servings_total
        sodium = info.sodium_mg * servings_total
        sugar = info.added_sugar_g * servings_total
        cost = info.unit_cost * scaled_qty

        total_kcal += kcal
        total_protein += protein
        total_carbs += carbs
        total_fat += fat
        total_sodium += sodium
        total_sugar += sugar
        total_cost += cost
        if info.category == "produce":
            produce_kcal += kcal

        lines.append(FoodLine(
            item=item_name, qty=round(scaled_qty, 1), unit=info.unit,
            servings_total=round(servings_total, 1),
            kcal_total=round(kcal), protein_g_total=round(protein),
            carbs_g_total=round(carbs), fat_g_total=round(fat), cost_total=round(cost, 2),
            per_serving_kcal=info.kcal, per_serving_protein=info.protein_g,
            per_serving_carbs=info.carbs_g, per_serving_fat=info.fat_g,
        ))

    produce_share = (produce_kcal / total_kcal * 100) if total_kcal else 0.0
    return PackageTotals(
        kcal=total_kcal, protein_g=total_protein, carbs_g=total_carbs, fat_g=total_fat,
        sodium_mg=total_sodium, added_sugar_g=total_sugar,
        produce_kcal_share_pct=produce_share, total_cost=round(total_cost, 2), lines=lines,
    )


def per_day(monthly_total: float) -> float:
    return monthly_total / DAYS_PER_MONTH


def per_week(monthly_total: float) -> float:
    return monthly_total / WEEKS_PER_MONTH


def normalize_income_to_monthly(amount: float, frequency: str) -> float:
    return amount / 12 if frequency == "Yearly" else amount


@dataclass
class BudgetResult:
    monthly_income: float
    total_expenses: float
    program_value: float
    leftover_cash: float
    weekly_leftover_cash: float
    is_shortfall: bool


def compute_budget(monthly_income: float, expenses: Dict[str, float], program_value: float) -> BudgetResult:
    total_expenses = sum(expenses.values())
    leftover = monthly_income - total_expenses
    return BudgetResult(
        monthly_income=monthly_income, total_expenses=total_expenses, program_value=program_value,
        leftover_cash=leftover, weekly_leftover_cash=leftover / WEEKS_PER_MONTH, is_shortfall=leftover < 0,
    )


def build_budget_summary_text(profile: "HouseholdProfile", program_value: float, monthly_income: float,
                                expenses: Dict[str, float], budget: BudgetResult) -> str:
    """Plain-text summary for the opt-in export — meant to be printed or
    handed to someone (a caseworker, a family member), not just read on
    screen. Nothing here is saved automatically; this text only exists
    because the person chose to save it. One combined packet: household and
    program details, the full FDPIR item breakdown when applicable, the
    budget, and the school-meals note — not separate fragments."""
    lines = [
        "GroundTruth — Summary",
        f"Generated locally on {date.today().isoformat()}. This file was not saved automatically —",
        "it exists only because you chose to save it; the app itself keeps nothing on disk.",
        "",
        f"Household size: {profile.household_size}",
    ]
    package_totals = None
    if profile.program == "FDPIR":
        lines.append(f"Program: FDPIR ({profile.agency_key})")
        package = FOOD_PACKAGES[profile.agency_key]
        package_totals = totals_for_package(package, profile.household_size)
    elif profile.program == "SNAP":
        lines.append(f"Program: SNAP (${profile.snap_balance:,.0f}/month balance)")

    if package_totals is not None:
        lines.append("")
        lines.append(f"FDPIR package details — {profile.agency_key} (scaled to household of "
                     f"{profile.household_size}):")
        lines.append(f"  Total grocery value: ${package_totals.total_cost:,.0f}/month "
                     f"(~${per_week(package_totals.total_cost):,.0f}/week)")
        lines.append(f"  Daily nutrition: {per_day(package_totals.kcal):,.0f} kcal, "
                     f"{per_day(package_totals.protein_g):,.0f}g protein, "
                     f"{per_day(package_totals.carbs_g):,.0f}g carbs, {per_day(package_totals.fat_g):,.0f}g fat")
        lines.append(f"  Sodium: {per_day(package_totals.sodium_mg):,.0f}mg/day; "
                     f"Added sugar: {per_day(package_totals.added_sugar_g):,.0f}g/day; "
                     f"{package_totals.produce_kcal_share_pct:,.0f}% of calories from produce")
        lines.append("  Item breakdown:")
        for line in sorted(package_totals.lines, key=lambda ln: -ln.kcal_total):
            lines.append(f"    - {line.item}: {line.qty} {line.unit} ({line.servings_total} servings) — "
                         f"{line.per_serving_kcal} kcal/{line.per_serving_protein}g P/{line.per_serving_carbs}g C/"
                         f"{line.per_serving_fat}g F per serving — ${line.cost_total:,.2f} total")

    lines.append("")
    lines.append(f"Monthly take-home pay: ${monthly_income:,.0f}")
    lines.append("")
    lines.append("Essential monthly expenses:")
    for cat, amount in expenses.items():
        lines.append(f"  - {cat}: ${amount:,.0f}")
    lines.append("")
    lines.append(f"Cash left after bills: ${budget.leftover_cash:,.0f}/month "
                 f"(~${budget.weekly_leftover_cash:,.0f}/week)")
    lines.append(f"Food benefit (separate from cash, covers groceries): ${budget.program_value:,.0f}/month")
    if budget.is_shortfall:
        lines.append("")
        lines.append("NOTE: essential expenses are estimated to exceed take-home pay this month.")
    if profile.has_school_age_children:
        lines.append("")
        if profile.program in ("FDPIR", "SNAP"):
            lines.append(f"School meals: since this household is enrolled in {profile.program}, school-age "
                         f"children are automatically eligible for free school meals via direct certification "
                         f"(USDA FNS Policy Memo FD-045) — no separate income application is needed.")
        free_t, reduced_t = nslp_income_thresholds_monthly(profile.household_size)
        lines.append(f"For reference, the 2026-2027 federal income guideline for a household of "
                     f"{profile.household_size}: free meals at or below ${free_t:,.0f}/month, reduced-price "
                     f"at or below ${reduced_t:,.0f}/month.")
    lines.append("")
    lines.append("Figures in this app are planning estimates, not an official benefits determination.")
    lines.append("Confirm current program amounts and eligibility with your local administering agency.")
    return "\n".join(lines)


# ===========================================================================
# UI LAYER
# ===========================================================================

BG = "#faf7f2"
CARD_BG = "#ffffff"
BORDER = "#d9d2c2"
ACCENT = "#5b6b3a"
ACCENT_DARK = "#3f4a28"
ACCENT_LIGHT = "#eef1e6"
TEXT = "#252520"
MUTED = "#5c5748"
WARN = "#a4522a"
ROW_ALT = "#f5f2ea"

TILE_COLORS = ["#5b6b3a", "#8a5a3b", "#3b6b78", "#7a4f6b", "#a68a2e"]  # sage, clay, teal, plum, ochre

FONT_HEAD = FONT_SUB = FONT_LABEL = FONT_LABEL_BOLD = FONT_BIG = FONT_SMALL = None
FONT_MENU_TITLE = FONT_MENU_DESC = FONT_CHIP = None
FONT_SECTION_HEAD = FONT_REGION_HEAD = FONT_ABOUT_HEAD = FONT_RECIPE_TITLE = None

# (family, base size, weight) for each named font — base sizes are what
# FONT_SCALE = 1.0 means; init_fonts() creates the real Font objects (which
# need a live Tk root to exist), and set_font_scale() rescales them all
# afterward without rebuilding a single widget, since every place in this
# file that does font=FONT_X is holding a reference to the same live object.
_FONT_SPECS = {
    "FONT_HEAD": ("Georgia", 24, "bold"),
    "FONT_SUB": ("Helvetica", 13, "normal"),
    "FONT_LABEL": ("Helvetica", 12, "normal"),
    "FONT_LABEL_BOLD": ("Helvetica", 12, "bold"),
    "FONT_BIG": ("Helvetica", 24, "bold"),
    "FONT_SMALL": ("Helvetica", 10, "normal"),
    "FONT_MENU_TITLE": ("Georgia", 16, "bold"),
    "FONT_MENU_DESC": ("Helvetica", 11, "normal"),
    "FONT_CHIP": ("Helvetica", 9, "bold"),
    "FONT_SECTION_HEAD": ("Georgia", 16, "bold"),
    "FONT_REGION_HEAD": ("Georgia", 12, "bold"),
    "FONT_ABOUT_HEAD": ("Georgia", 15, "bold"),
    "FONT_RECIPE_TITLE": ("Georgia", 18, "bold"),
}

FONT_SCALE_MIN = 0.85
FONT_SCALE_MAX = 1.5
_current_font_scale = 1.0


def init_fonts(root: tk.Tk) -> None:
    """Create the real Font objects. Must run once, after the Tk root
    exists and before any page widgets are built."""
    global FONT_HEAD, FONT_SUB, FONT_LABEL, FONT_LABEL_BOLD, FONT_BIG, FONT_SMALL
    global FONT_MENU_TITLE, FONT_MENU_DESC, FONT_CHIP
    global FONT_SECTION_HEAD, FONT_REGION_HEAD, FONT_ABOUT_HEAD, FONT_RECIPE_TITLE

    created = {}
    for name, (family, size, weight) in _FONT_SPECS.items():
        created[name] = tkfont.Font(root=root, family=family, size=size, weight=weight)

    FONT_HEAD = created["FONT_HEAD"]
    FONT_SUB = created["FONT_SUB"]
    FONT_LABEL = created["FONT_LABEL"]
    FONT_LABEL_BOLD = created["FONT_LABEL_BOLD"]
    FONT_BIG = created["FONT_BIG"]
    FONT_SMALL = created["FONT_SMALL"]
    FONT_MENU_TITLE = created["FONT_MENU_TITLE"]
    FONT_MENU_DESC = created["FONT_MENU_DESC"]
    FONT_CHIP = created["FONT_CHIP"]
    FONT_SECTION_HEAD = created["FONT_SECTION_HEAD"]
    FONT_REGION_HEAD = created["FONT_REGION_HEAD"]
    FONT_ABOUT_HEAD = created["FONT_ABOUT_HEAD"]
    FONT_RECIPE_TITLE = created["FONT_RECIPE_TITLE"]


_BASE_TREEVIEW_ROWHEIGHT = 32


def set_font_scale(scale: float) -> None:
    """Rescale every named font in place. Because these are live Font
    objects (not tuples) and every widget in the app was configured with a
    reference to one of them, calling .configure() here updates all of them
    immediately — no widget needs to be rebuilt."""
    global _current_font_scale
    _current_font_scale = max(FONT_SCALE_MIN, min(FONT_SCALE_MAX, scale))

    name_to_font = {
        "FONT_HEAD": FONT_HEAD, "FONT_SUB": FONT_SUB, "FONT_LABEL": FONT_LABEL,
        "FONT_LABEL_BOLD": FONT_LABEL_BOLD, "FONT_BIG": FONT_BIG, "FONT_SMALL": FONT_SMALL,
        "FONT_MENU_TITLE": FONT_MENU_TITLE, "FONT_MENU_DESC": FONT_MENU_DESC, "FONT_CHIP": FONT_CHIP,
        "FONT_SECTION_HEAD": FONT_SECTION_HEAD, "FONT_REGION_HEAD": FONT_REGION_HEAD,
        "FONT_ABOUT_HEAD": FONT_ABOUT_HEAD, "FONT_RECIPE_TITLE": FONT_RECIPE_TITLE,
    }
    for name, font_obj in name_to_font.items():
        if font_obj is None:
            continue
        _, base_size, _ = _FONT_SPECS[name]
        font_obj.configure(size=round(base_size * _current_font_scale))

    # The Treeview's row height is a fixed pixel value in the ttk style, not
    # something that follows its font automatically — without rescaling it
    # too, larger text would get clipped inside unchanged-height rows.
    try:
        ttk.Style().configure("Treeview", rowheight=round(_BASE_TREEVIEW_ROWHEIGHT * _current_font_scale))
    except tk.TclError:
        pass  # no ttk style engine yet (e.g. called before any App exists)


def get_font_scale() -> float:
    return _current_font_scale


def configure_styles(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD_BG)

    style.configure("Accent.TButton", font=FONT_LABEL_BOLD, foreground="white",
                     background=ACCENT, borderwidth=0, padding=(20, 12))
    style.map("Accent.TButton", background=[("active", ACCENT_DARK), ("pressed", ACCENT_DARK)])

    style.configure("Ghost.TButton", font=FONT_LABEL, foreground=ACCENT_DARK,
                     background=BG, borderwidth=0, padding=(10, 6))
    style.map("Ghost.TButton", background=[("active", ACCENT_LIGHT)])

    style.configure("Toggle.TButton", font=FONT_LABEL_BOLD, foreground=TEXT,
                     background="white", borderwidth=1, relief="solid", padding=(24, 14))
    style.map("Toggle.TButton", background=[("active", ACCENT_LIGHT)])

    style.configure("ToggleSelected.TButton", font=FONT_LABEL_BOLD, foreground="white",
                     background=ACCENT, borderwidth=1, relief="solid", padding=(24, 14))
    style.map("ToggleSelected.TButton", background=[("active", ACCENT_DARK)])

    style.configure("TEntry", fieldbackground="white", foreground=TEXT,
                     bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=8, font=FONT_LABEL)
    style.map("TEntry", bordercolor=[("focus", ACCENT)])

    style.configure("TSpinbox", fieldbackground="white", foreground=TEXT,
                     bordercolor=BORDER, arrowsize=16, padding=6, font=FONT_LABEL)
    style.map("TSpinbox", bordercolor=[("focus", ACCENT)])

    style.configure("TCombobox", fieldbackground="white", foreground=TEXT, bordercolor=BORDER,
                     padding=8, font=FONT_LABEL)
    style.map("TCombobox", bordercolor=[("focus", ACCENT)])

    style.configure("TRadiobutton", background=CARD_BG, foreground=TEXT, font=FONT_LABEL)
    style.configure("TCheckbutton", background=CARD_BG, foreground=TEXT, font=FONT_LABEL)

    style.configure("Treeview", font=FONT_LABEL, rowheight=32, fieldbackground="white",
                     background="white", bordercolor=BORDER, borderwidth=1)
    style.configure("Treeview.Heading", font=FONT_LABEL_BOLD, background=ACCENT_DARK,
                     foreground="white", padding=(8, 8), relief="flat")
    style.map("Treeview.Heading", background=[("active", ACCENT_DARK)])
    style.map("Treeview", background=[("selected", ACCENT_LIGHT)], foreground=[("selected", TEXT)])

    style.configure("Vertical.TScrollbar", background=BORDER, troughcolor=BG, arrowsize=14)
    style.configure("Nav.Horizontal.TProgressbar", troughcolor=BORDER, background=ACCENT,
                     bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT)


# --- small reusable widgets --------------------------------------------------

class ScrollableFrame(tk.Frame):
    """A vertically scrollable container. Put content inside `.body`.

    Mousewheel handling is bound directly to this canvas (not bind_all), so
    scrolling only ever affects the widget under the cursor — this avoids a
    class of cross-page interference bugs that a global bind_all/unbind_all
    pattern is prone to when several scrollable pages exist at once.
    """

    def __init__(self, parent, bg=BG):
        super().__init__(parent, bg=bg)
        self.canvas = canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.body = tk.Frame(canvas, bg=bg)

        self.body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        window_id = canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Without this, the embedded body only ever sizes to its content's
        # natural width, so it can be narrower than the visible canvas —
        # leaving no actual room for a centered child (like the recipes
        # grid) to center within. Stretching it to the canvas's width fixes
        # that and makes every page's content consistently fill the window.
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window_id, width=e.width))

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _wheel(event):
            num = getattr(event, "num", None)
            delta = -1 if num == 4 else (1 if num == 5 else -int(event.delta / 120))
            canvas.yview_scroll(delta, "units")

        canvas.bind("<MouseWheel>", _wheel)
        canvas.bind("<Button-4>", _wheel)
        canvas.bind("<Button-5>", _wheel)


class SummaryCard(tk.Frame):
    def __init__(self, parent, title: str):
        super().__init__(parent, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1)
        tk.Label(self, text=title, font=FONT_LABEL_BOLD, bg=CARD_BG, fg=TEXT).pack(
            anchor="w", padx=18, pady=(16, 4))
        self.value_lbl = tk.Label(self, text="—", font=FONT_BIG, bg=CARD_BG, fg=ACCENT_DARK)
        self.value_lbl.pack(anchor="w", padx=18)
        self.sub_lbl = tk.Label(self, text="", font=FONT_SMALL, bg=CARD_BG, fg=MUTED,
                                 wraplength=210, justify="left")
        self.sub_lbl.pack(anchor="w", padx=18, pady=(2, 16))

    def set(self, value: str, subtext: str, warn: bool = False):
        self.value_lbl.config(text=value, fg=WARN if warn else ACCENT_DARK)
        self.sub_lbl.config(text=subtext)


def build_navbar(parent, controller, title: str):
    bar = tk.Frame(parent, bg=BG)
    bar.pack(fill="x", padx=28, pady=(18, 4))
    ttk.Button(bar, text="← Home", style="Ghost.TButton", cursor="hand2",
               command=lambda: controller.show_frame("MainMenu")).pack(side="left")
    tk.Label(bar, text=title, font=FONT_HEAD, bg=BG, fg=TEXT).pack(side="left", padx=(18, 0))


def clear_frame(frame: tk.Widget):
    for widget in frame.winfo_children():
        widget.destroy()


def make_chip(parent, text: str, color: str) -> tk.Label:
    return tk.Label(parent, text=text, font=FONT_CHIP, bg=color, fg="white", padx=8, pady=2)


class ToggleChip(tk.Label):
    """A clickable pill that toggles between an inactive and active look —
    used for the dietary-tag and allergen filters, which need to actually
    filter, not just decorate."""

    def __init__(self, parent, text: str, active_color: str, on_toggle):
        super().__init__(parent, text=text, font=FONT_CHIP, padx=8, pady=3, cursor="hand2")
        self.active_color = active_color
        self.on_toggle = on_toggle
        self.is_active = False
        self._apply_style()
        self.bind("<Button-1>", self._clicked)

    def _apply_style(self):
        if self.is_active:
            self.configure(bg=self.active_color, fg="white")
        else:
            self.configure(bg=BORDER, fg=TEXT)

    def _clicked(self, _event):
        self.is_active = not self.is_active
        self._apply_style()
        self.on_toggle(self.is_active)


class MenuTile(tk.Frame):
    """A clickable, wide main-menu row with a colored accent stripe, a bold
    title, and a muted description — used in a vertical list on the menu."""

    def __init__(self, parent, title: str, desc: str, accent: str, command):
        super().__init__(parent, bg="white", highlightbackground=BORDER, highlightthickness=1, cursor="hand2")
        self.command = command

        stripe = tk.Frame(self, bg=accent, width=6)
        stripe.pack(side="left", fill="y")

        text_area = tk.Frame(self, bg="white")
        text_area.pack(side="left", fill="both", expand=True)
        self.title_lbl = tk.Label(text_area, text=title, font=FONT_MENU_TITLE, bg="white", fg=TEXT)
        self.title_lbl.pack(anchor="w", padx=18, pady=(9, 1))
        self.desc_lbl = tk.Label(text_area, text=desc, font=FONT_MENU_DESC, bg="white", fg=MUTED,
                                  wraplength=680, justify="left")
        self.desc_lbl.pack(anchor="w", padx=18, pady=(0, 9))

        for widget in (self, stripe, text_area, self.title_lbl, self.desc_lbl):
            widget.bind("<Button-1>", lambda e: self.command())
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def _on_enter(self, _e):
        self.configure(bg=ACCENT_LIGHT)
        for w in (self.title_lbl.master,):
            w.configure(bg=ACCENT_LIGHT)
        self.title_lbl.configure(bg=ACCENT_LIGHT)
        self.desc_lbl.configure(bg=ACCENT_LIGHT)

    def _on_leave(self, _e):
        self.configure(bg="white")
        self.title_lbl.master.configure(bg="white")
        self.title_lbl.configure(bg="white")
        self.desc_lbl.configure(bg="white")


# --- Main menu ----------------------------------------------------------------

class MainMenuPage(tk.Frame):
    MAX_CONTENT_WIDTH = 760
    MAX_CONTENT_HEIGHT = 680

    def __init__(self, parent, controller):
        super().__init__(parent, bg=BG)
        self.controller = controller

        self.bg_canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.bind("<Configure>", self._draw_background)

        self.content = content = tk.Frame(self, bg=BG)
        self._reposition_content()

        header = tk.Frame(content, bg=BG)
        header.pack(fill="x", pady=(6, 6))
        tk.Label(header, text="GroundTruth", font=FONT_HEAD, bg=BG, fg=TEXT).pack(anchor="w")
        tk.Label(header, text="The Household Food Navigator", font=FONT_SUB, bg=BG, fg=ACCENT_DARK).pack(anchor="w", pady=(2, 0))
        tk.Label(header, text="Compare food programs in real dollars, budget around them, "
                              "find recipes, and locate a distribution site — all offline.",
                 font=FONT_SUB, bg=BG, fg=MUTED, wraplength=760, justify="left").pack(anchor="w", pady=(6, 0))
        tk.Label(header, text=f"Runs fully offline · data last bundled {date.today().isoformat()}",
                 font=FONT_SMALL, bg=BG, fg=MUTED).pack(anchor="w", pady=(8, 0))

        self.status_frame = tk.Frame(content, bg=BG)
        self.status_frame.pack(fill="x", pady=(4, 0))

        tiles_area = tk.Frame(content, bg=BG)
        tiles_area.pack(fill="both", expand=True, pady=16)

        tiles = [
            ("Calculator", "Compare FDPIR or SNAP value, item by item, against your household.", "Calculator"),
            ("Finances", "Jump straight to your budget — income, expenses, and what's left over.", "Finances"),
            ("Recipes", "Cost and nutrition per serving, with step-by-step directions.", "Recipes"),
            ("Locator", "Find the nearest FDPIR distribution site by ZIP code.", "Locator"),
            ("About", "What FDPIR and SNAP are, data privacy, and sourced statistics.", "About"),
        ]
        for i, (title, desc, target) in enumerate(tiles):
            tile = MenuTile(tiles_area, title, desc, TILE_COLORS[i % len(TILE_COLORS)],
                             command=lambda t=target: controller.show_frame(t))
            tile.pack(fill="x", pady=4)

    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        self._render_status()

    def _render_status(self):
        clear_frame(self.status_frame)
        profile = self.controller.profile
        if profile.program is None:
            return  # nothing set up yet — no status to show

        if profile.program == "FDPIR":
            detail = f"FDPIR ({profile.agency_key})"
        else:
            detail = f"SNAP (${profile.snap_balance:,.0f}/mo)"
        text = f"Household of {profile.household_size} · {detail}"

        budget = self.controller.last_budget
        warn = False
        if budget is not None:
            text += f" · ${budget.leftover_cash:,.0f}/mo left after bills"
            warn = budget.is_shortfall

        card = tk.Frame(self.status_frame, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x")
        tk.Label(card, text=text, font=FONT_LABEL_BOLD, bg=CARD_BG, fg=WARN if warn else ACCENT_DARK,
                 wraplength=720, justify="left").pack(anchor="w", padx=16, pady=10)

    def _reposition_content(self):
        w = self.winfo_width() or 1140
        h = self.winfo_height() or 800
        content_w = min(self.MAX_CONTENT_WIDTH, int(w * 0.82))
        content_h = min(self.MAX_CONTENT_HEIGHT, int(h * 0.86))
        self.content.place(relx=0.5, rely=0.5, anchor="center", width=content_w, height=content_h)

    def _draw_background(self, _event=None):
        self._reposition_content()
        c = self.bg_canvas
        c.delete("all")
        w = self.winfo_width() or 1040
        h = self.winfo_height() or 800
        c.create_rectangle(0, 0, w, 6, fill=ACCENT, outline="")

        # Large soft corner blooms
        c.create_oval(-150, -150, 280, 280, fill=ACCENT_LIGHT, outline="")
        c.create_oval(w - 280, -140, w + 150, 230, fill="#e7ded0", outline="")
        c.create_oval(-170, h - 260, 220, h + 170, fill="#eef1e6", outline="")
        c.create_oval(w - 250, h - 250, w + 170, h + 170, fill="#e3e8d6", outline="")

        # Extra mid-field blooms — more compact tiles leave more open space
        # to fill, so this covers it with shapes rather than blank canvas.
        c.create_oval(int(w * 0.35), int(h * 0.80), int(w * 0.35) + 150, int(h * 0.80) + 150,
                      fill="#f0e6d8", outline="")
        c.create_oval(int(w * 0.58), int(h * 0.06), int(w * 0.58) + 130, int(h * 0.06) + 130,
                      fill="#f3ede1", outline="")
        c.create_oval(int(w * 0.06), int(h * 0.42), int(w * 0.06) + 110, int(h * 0.42) + 110,
                      fill="#eef2e4", outline="")
        c.create_oval(int(w * 0.88), int(h * 0.52), int(w * 0.88) + 140, int(h * 0.52) + 140,
                      fill="#e9e2d2", outline="")
        c.create_oval(int(w * 0.20), int(h * 0.05), int(w * 0.20) + 90, int(h * 0.05) + 90,
                      fill="#eef1e6", outline="")

        # Thin outline rings for a bit of texture variety beyond solid blobs
        for cx_frac, cy_frac, r, color in [(0.18, 0.16, 55, "#ded5c2"), (0.83, 0.86, 48, "#d8ddc8"),
                                            (0.50, 0.94, 36, "#e6ded0"), (0.94, 0.20, 40, "#e2ddc9")]:
            cx, cy = int(w * cx_frac), int(h * cy_frac)
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=2)

        # A small dot-grid texture along the right edge for extra detail
        dot_color = "#ece5d6"
        for row in range(7):
            for col in range(3):
                x = w - 66 + col * 20
                y = 100 + row * 80
                c.create_oval(x - 3, y - 3, x + 3, y + 3, fill=dot_color, outline="")


# --- Calculator wizard ---------------------------------------------------------

class HouseholdProfile:
    """Shared, in-memory household state — set from the Calculator or the
    Finances page, read by both (and by Recipes, for its package filter).
    Never written to disk; gone when the app closes."""

    def __init__(self):
        self.household_size = 4
        self.program: Optional[str] = None
        self.agency_key: Optional[str] = list(FOOD_PACKAGES.keys())[0]
        self.snap_balance = 0.0
        self.salary_amount = 0.0
        self.salary_frequency = "Monthly"
        self.expenses: Dict[str, float] = {cat: 0.0 for cat in EXPENSE_CATEGORIES}
        self.has_school_age_children = False


def build_program_picker(parent, profile: "HouseholdProfile"):
    """Draws the FDPIR/SNAP toggle plus the bulleted, region-grouped agency
    list or the SNAP balance field — pre-filled from profile, but not
    committed to it. Returns (program_var, agency_var, snap_var) for the
    caller to validate and commit on its own action button, so this one
    picker works for both the Calculator wizard and the Finances page."""
    toggle_row = tk.Frame(parent, bg=CARD_BG)
    toggle_row.pack(anchor="w")
    detail_area = tk.Frame(parent, bg=CARD_BG)
    detail_area.pack(fill="x", pady=(16, 0))

    program_var = tk.StringVar(value=profile.program or "")
    agency_var = tk.StringVar(value=profile.agency_key or list(FOOD_PACKAGES.keys())[0])
    snap_var = tk.StringVar(value=str(profile.snap_balance) if profile.snap_balance else "")

    fdpir_btn = ttk.Button(toggle_row, text="FDPIR", cursor="hand2")
    snap_btn = ttk.Button(toggle_row, text="SNAP", cursor="hand2")
    fdpir_btn.pack(side="left")
    snap_btn.pack(side="left", padx=(12, 0))

    def refresh_toggle_styles():
        fdpir_btn.configure(style="ToggleSelected.TButton" if program_var.get() == "FDPIR" else "Toggle.TButton")
        snap_btn.configure(style="ToggleSelected.TButton" if program_var.get() == "SNAP" else "Toggle.TButton")

    def show_detail():
        clear_frame(detail_area)
        if program_var.get() == "FDPIR":
            tk.Label(detail_area, text="Which agency administers your FDPIR package?",
                     font=FONT_LABEL_BOLD, bg=CARD_BG, fg=TEXT).pack(anchor="w")
            for region in AGENCY_REGIONS:
                agencies_in_region = [k for k, v in FOOD_PACKAGES.items() if v.region == region]
                if not agencies_in_region:
                    continue
                tk.Label(detail_area, text=region, font=FONT_REGION_HEAD, bg=CARD_BG,
                         fg=ACCENT_DARK).pack(anchor="w", pady=(12, 2))
                for key in agencies_in_region:
                    ttk.Radiobutton(detail_area, text=f"•  {key}", value=key, variable=agency_var,
                                    style="TRadiobutton").pack(anchor="w", padx=(12, 0), pady=1)
        elif program_var.get() == "SNAP":
            tk.Label(detail_area, text="Monthly SNAP balance ($)", font=FONT_LABEL_BOLD,
                     bg=CARD_BG, fg=TEXT).pack(anchor="w")
            ttk.Entry(detail_area, textvariable=snap_var, width=12, font=FONT_LABEL).pack(anchor="w", pady=(8, 0))

    def pick(program):
        program_var.set(program)
        refresh_toggle_styles()
        show_detail()

    fdpir_btn.configure(command=lambda: pick("FDPIR"))
    snap_btn.configure(command=lambda: pick("SNAP"))
    refresh_toggle_styles()
    show_detail()

    return program_var, agency_var, snap_var


def build_finances_section(parent, profile: "HouseholdProfile", controller, program_value: float):
    """The expense form + Calculate Budget button + results. Shared between
    the Calculator's results step and the standalone Finances page."""
    card = tk.Frame(parent, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1)
    card.pack(fill="x", pady=(0, 14))
    inner = tk.Frame(card, bg=CARD_BG)
    inner.pack(fill="x", padx=22, pady=20)
    tk.Label(inner, text="Finances", font=FONT_SECTION_HEAD, bg=CARD_BG, fg=ACCENT_DARK).pack(anchor="w")
    monthly_income = normalize_income_to_monthly(profile.salary_amount, profile.salary_frequency)
    tk.Label(inner, text=f"Monthly take-home pay: ${monthly_income:,.0f}", font=FONT_LABEL,
             bg=CARD_BG, fg=TEXT).pack(anchor="w", pady=(4, 12))

    tk.Label(inner, text="Essential monthly expenses", font=FONT_LABEL_BOLD, bg=CARD_BG, fg=TEXT).pack(anchor="w")

    gas_cost = getattr(controller, "shared_gas_cost", None)
    if gas_cost:
        tk.Label(inner, text=f"Travel to distribution site is pre-filled at ${gas_cost:,.0f}/mo from "
                              f"the Locator page — edit it if that's not right.",
                 font=FONT_SMALL, bg=CARD_BG, fg=MUTED, wraplength=700, justify="left").pack(
            anchor="w", pady=(2, 6))

    expense_vars: Dict[str, tk.StringVar] = {}
    for cat in EXPENSE_CATEGORIES:
        row = tk.Frame(inner, bg=CARD_BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=cat, font=FONT_LABEL, bg=CARD_BG, fg=TEXT, width=26, anchor="w").pack(side="left")
        existing = profile.expenses.get(cat, 0.0)
        if not existing and cat == "Travel to distribution site" and gas_cost:
            existing = gas_cost
        var = tk.StringVar(value=str(existing) if existing else "")
        ttk.Entry(row, textvariable=var, width=12, font=FONT_LABEL).pack(side="left")
        expense_vars[cat] = var

    results_area = tk.Frame(inner, bg=CARD_BG)
    results_area.pack(fill="x", pady=(14, 0))

    def calculate_budget():
        expenses = {}
        for cat, var in expense_vars.items():
            try:
                val = float(var.get() or 0)
                if val < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Check expenses", f"Enter a number of 0 or more for {cat}.")
                return
            expenses[cat] = val
        profile.expenses = expenses

        budget = compute_budget(monthly_income, expenses, program_value)
        controller.last_budget = budget
        clear_frame(results_area)

        cards_row = tk.Frame(results_area, bg=CARD_BG)
        cards_row.pack(fill="x")
        c1 = SummaryCard(cards_row, "Cash left after bills")
        c1.pack(side="left", expand=True, fill="both", padx=(0, 6))
        c1.set(f"${budget.leftover_cash:,.0f}/mo", f"~${budget.weekly_leftover_cash:,.0f}/week",
               warn=budget.is_shortfall)

        c2 = SummaryCard(cards_row, "Food benefit (separate from cash)")
        c2.pack(side="left", expand=True, fill="both", padx=(6, 0))
        c2.set(f"${budget.program_value:,.0f}/mo", "Covers groceries — not spendable cash")

        if budget.is_shortfall:
            tk.Label(results_area, text="Essential expenses are estimated to exceed take-home pay this "
                                         "month. Consider reviewing which expenses are flexible, or "
                                         "contacting a local assistance office for support beyond food.",
                     font=FONT_LABEL, bg=CARD_BG, fg=WARN, wraplength=760, justify="left").pack(
                anchor="w", pady=(10, 0))

        def save_summary():
            path = filedialog.asksaveasfilename(
                title="Save budget summary", defaultextension=".txt",
                filetypes=[("Text file", "*.txt")], initialfile="food-navigator-budget-summary.txt",
            )
            if not path:
                return  # user cancelled — nothing saved, nothing to report
            try:
                summary = build_budget_summary_text(profile, program_value, monthly_income, expenses, budget)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(summary)
                messagebox.showinfo("Saved", f"Budget summary saved to:\n{path}")
            except OSError as e:
                messagebox.showerror("Couldn't save", f"Something went wrong saving the file:\n{e}")

        ttk.Button(results_area, text="Save Summary as Text File", style="Ghost.TButton", cursor="hand2",
                   command=save_summary).pack(anchor="w", pady=(12, 0))

    ttk.Button(inner, text="Calculate Budget", style="Accent.TButton", cursor="hand2",
               command=calculate_budget).pack(anchor="w", pady=(16, 0))


def build_school_meals_section(parent, profile: "HouseholdProfile"):
    card = tk.Frame(parent, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1)
    card.pack(fill="x", pady=(0, 14))
    inner = tk.Frame(card, bg=CARD_BG)
    inner.pack(fill="x", padx=22, pady=20)
    tk.Label(inner, text="School meals", font=FONT_SECTION_HEAD, bg=CARD_BG, fg=ACCENT_DARK).pack(anchor="w")

    if profile.program in ("FDPIR", "SNAP"):
        tk.Label(inner, text=f"Since your household is enrolled in {profile.program}, your school-age "
                              f"children are automatically eligible for free school meals through "
                              f"\"direct certification\" — no separate income application is needed for "
                              f"that eligibility. (Source: USDA FNS Policy Memo FD-045)",
                 font=FONT_LABEL, bg=CARD_BG, fg=TEXT, wraplength=760, justify="left").pack(
            anchor="w", pady=(6, 12))

    free_thresh, reduced_thresh = nslp_income_thresholds_monthly(profile.household_size)
    tk.Label(inner, text=f"For reference, the 2026-2027 federal income guideline for a household of "
                          f"{profile.household_size}: free meals at or below ${free_thresh:,.0f}/month, "
                          f"reduced-price at or below ${reduced_thresh:,.0f}/month. This applies "
                          f"regardless of FDPIR/SNAP status and may be relevant for other programs, like "
                          f"Head Start. (Source: USDA FNS Child Nutrition Income Eligibility Guidelines, "
                          f"130%/185% of the HHS poverty guideline)",
             font=FONT_SMALL, bg=CARD_BG, fg=MUTED, wraplength=760, justify="left").pack(anchor="w")


class CalculatorPage(tk.Frame):
    TOTAL_STEPS = 4

    def __init__(self, parent, controller):
        super().__init__(parent, bg=BG)
        self.controller = controller
        self.current_step = 1

        build_navbar(self, controller, "Calculator")

        progress_row = tk.Frame(self, bg=BG)
        progress_row.pack(fill="x", padx=28, pady=(4, 4))
        self.step_label = tk.Label(progress_row, text="", font=FONT_LABEL_BOLD, bg=BG, fg=ACCENT_DARK)
        self.step_label.pack(anchor="w")
        self.progress = ttk.Progressbar(progress_row, style="Nav.Horizontal.TProgressbar",
                                          maximum=self.TOTAL_STEPS, length=300)
        self.progress.pack(anchor="w", pady=(4, 0))

        scroller = ScrollableFrame(self)
        scroller.pack(fill="both", expand=True, padx=28, pady=(8, 20))
        self.scroller = scroller
        self.step_area = scroller.body

        self._render_step()

    @property
    def state(self) -> HouseholdProfile:
        return self.controller.profile

    def _render_step(self):
        clear_frame(self.step_area)
        # Step N of TOTAL fills the bar to N/TOTAL, so step 4 of 4 reads full.
        self.progress["value"] = self.current_step
        step_names = {1: "Household size", 2: "FDPIR or SNAP", 3: "Salary", 4: "Results & finances"}
        self.step_label.config(text=f"Step {self.current_step} of {self.TOTAL_STEPS}: {step_names[self.current_step]}")

        if self.current_step == 1:
            self._build_step1()
        elif self.current_step == 2:
            self._build_step2()
        elif self.current_step == 3:
            self._build_step3()
        elif self.current_step == 4:
            self._build_results()

        # A tall step (like Results) can leave the scroll position deep down
        # the page; without resetting it, switching to a shorter step (e.g.
        # via Back) can leave the new content scrolled out of view entirely,
        # which looks exactly like a blank, unusable screen.
        self.step_area.update_idletasks()
        self.scroller.canvas.yview_moveto(0)

    def _card(self, parent) -> tk.Frame:
        card = tk.Frame(parent, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", pady=(0, 14))
        return card

    def _nav_buttons(self, parent, on_continue, continue_label="Continue"):
        row = tk.Frame(parent, bg=CARD_BG)
        row.pack(fill="x", padx=22, pady=(6, 18))
        if self.current_step > 1:
            ttk.Button(row, text="← Back", style="Ghost.TButton", cursor="hand2",
                       command=self._go_back).pack(side="left")
        ttk.Button(row, text=continue_label, style="Accent.TButton", cursor="hand2",
                   command=on_continue).pack(side="left", padx=(12, 0))

    def _go_back(self):
        self.current_step -= 1
        self._render_step()

    # -- step 1 --------------------------------------------------------
    def _build_step1(self):
        card = self._card(self.step_area)
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="x", padx=22, pady=20)
        tk.Label(inner, text="How many people are in your household?", font=FONT_LABEL_BOLD,
                 bg=CARD_BG, fg=TEXT).pack(anchor="w")
        var = tk.IntVar(value=self.state.household_size)
        box = ttk.Spinbox(inner, from_=1, to=12, textvariable=var, width=6, font=FONT_LABEL, justify="center")
        box.pack(anchor="w", pady=(10, 0))
        box.focus_set()

        def cont():
            try:
                size = int(var.get())
                if size < 1:
                    raise ValueError
            except (tk.TclError, ValueError):
                messagebox.showerror("Check household size", "Household size must be a whole number of 1 or more.")
                return
            self.state.household_size = size
            self.current_step = 2
            self._render_step()

        box.bind("<Return>", lambda e: cont())
        self._nav_buttons(card, cont)

    # -- step 2: program + bulleted, grouped agency picker -----------------
    def _build_step2(self):
        card = self._card(self.step_area)
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="x", padx=22, pady=20)
        tk.Label(inner, text="Which food program applies to your household?", font=FONT_LABEL_BOLD,
                 bg=CARD_BG, fg=TEXT).pack(anchor="w")
        tk.Label(inner, text="A household is enrolled in FDPIR or SNAP, not both — pick whichever "
                              "one currently applies.", font=FONT_SMALL, bg=CARD_BG, fg=MUTED,
                 wraplength=700, justify="left").pack(anchor="w", pady=(4, 12))

        program_var, agency_var, snap_var = build_program_picker(inner, self.state)

        def cont():
            program = program_var.get()
            if program not in ("FDPIR", "SNAP"):
                messagebox.showerror("Choose a program", "Select FDPIR or SNAP to continue.")
                return
            if program == "SNAP":
                try:
                    balance = float(snap_var.get() or 0)
                    if balance < 0:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("Check SNAP balance", "Enter a SNAP balance of 0 or more.")
                    return
                self.state.snap_balance = balance
            else:
                self.state.agency_key = agency_var.get()
            self.state.program = program
            self.current_step = 3
            self._render_step()

        self._nav_buttons(card, cont)

    # -- step 3 --------------------------------------------------------
    def _build_step3(self):
        card = self._card(self.step_area)
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="x", padx=22, pady=20)
        tk.Label(inner, text="What does your household bring home?", font=FONT_LABEL_BOLD,
                 bg=CARD_BG, fg=TEXT).pack(anchor="w")
        tk.Label(inner, text="Use take-home pay (after taxes), not gross salary — used only for the "
                              "budget in the next step and never leaves this device.",
                 font=FONT_SMALL, bg=CARD_BG, fg=MUTED, wraplength=700, justify="left").pack(
            anchor="w", pady=(4, 12))

        row = tk.Frame(inner, bg=CARD_BG)
        row.pack(anchor="w")
        amount_var = tk.StringVar(value=str(self.state.salary_amount) if self.state.salary_amount else "")
        entry = ttk.Entry(row, textvariable=amount_var, width=14, font=FONT_LABEL)
        entry.pack(side="left")
        freq_var = tk.StringVar(value=self.state.salary_frequency)
        ttk.Radiobutton(row, text="Monthly", value="Monthly", variable=freq_var).pack(side="left", padx=(16, 0))
        ttk.Radiobutton(row, text="Yearly", value="Yearly", variable=freq_var).pack(side="left", padx=(8, 0))

        school_var = tk.BooleanVar(value=self.state.has_school_age_children)
        ttk.Checkbutton(inner, text="We have school-age children (K-12) in the household",
                        variable=school_var).pack(anchor="w", pady=(16, 0))

        def cont():
            try:
                amount = float(amount_var.get() or 0)
                if amount < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Check income", "Enter take-home pay as a number of 0 or more.")
                return
            self.state.salary_amount = amount
            self.state.salary_frequency = freq_var.get()
            self.state.has_school_age_children = school_var.get()
            self.current_step = 4
            self._render_step()

        entry.bind("<Return>", lambda e: cont())
        self._nav_buttons(card, cont, continue_label="Calculate")

    # -- step 4 ----------------------------------------------------------
    def _build_results(self):
        state = self.state
        if state.program == "FDPIR":
            package = FOOD_PACKAGES[state.agency_key]
            totals = totals_for_package(package, state.household_size)
            self._build_fdpir_summary(package, totals, state.household_size)
            program_value = totals.total_cost
        else:
            self._build_snap_summary(state.snap_balance)
            program_value = state.snap_balance

        build_finances_section(self.step_area, state, self.controller, program_value)

        if state.has_school_age_children:
            build_school_meals_section(self.step_area, state)

        restart_row = tk.Frame(self.step_area, bg=BG)
        restart_row.pack(fill="x", pady=(4, 0))
        ttk.Button(restart_row, text="← Back", style="Ghost.TButton", cursor="hand2",
                   command=self._go_back).pack(side="left")
        ttk.Button(restart_row, text="Start Over", style="Ghost.TButton", cursor="hand2",
                   command=self._start_over).pack(side="left", padx=(12, 0))

    def _start_over(self):
        self.controller.profile = HouseholdProfile()
        self.current_step = 1
        self._render_step()

    def _build_fdpir_summary(self, package: FDPIRPackage, totals: PackageTotals, household: int):
        cards_row = tk.Frame(self.step_area, bg=BG)
        cards_row.pack(fill="x", pady=(0, 4))
        c1 = SummaryCard(cards_row, "Total grocery value")
        c1.pack(side="left", expand=True, fill="both", padx=(0, 6))
        c1.set(f"${totals.total_cost:,.0f}/mo", f"~${per_week(totals.total_cost):,.0f}/week for a household of {household}")

        c2 = SummaryCard(cards_row, "Daily calories & protein")
        c2.pack(side="left", expand=True, fill="both", padx=6)
        c2.set(f"{per_day(totals.kcal):,.0f} kcal", f"{per_day(totals.protein_g):,.0f}g protein/day")

        c3 = SummaryCard(cards_row, "Daily carbs & fat")
        c3.pack(side="left", expand=True, fill="both", padx=6)
        c3.set(f"{per_day(totals.carbs_g):,.0f}g / {per_day(totals.fat_g):,.0f}g",
               f"carbs / fat per day · {totals.produce_kcal_share_pct:,.0f}% of calories from produce")

        sodium_limit = DAILY_SODIUM_GUIDELINE_MG_PER_PERSON * household
        sugar_limit = DAILY_ADDED_SUGAR_GUIDELINE_G_PER_PERSON * household
        daily_sodium, daily_sugar = per_day(totals.sodium_mg), per_day(totals.added_sugar_g)
        c4 = SummaryCard(cards_row, "Sodium & added sugar")
        c4.pack(side="left", expand=True, fill="both", padx=(6, 0))
        sodium_flag = "above general guideline" if daily_sodium > sodium_limit else "within guideline"
        sugar_flag = "above general guideline" if daily_sugar > sugar_limit else "within guideline"
        c4.set(f"{daily_sodium:,.0f}mg / {daily_sugar:,.0f}g", f"sodium ({sodium_flag}), sugar ({sugar_flag})",
               warn=(daily_sodium > sodium_limit or daily_sugar > sugar_limit))

        table_card = self._card(self.step_area)
        tk.Label(table_card, text=f"{package.agency} — this month's package, scaled to your household",
                 font=FONT_LABEL_BOLD, bg=CARD_BG, fg=TEXT).pack(anchor="w", padx=18, pady=(16, 8))

        # "Quantity" and "Unit type" are separate columns so it's never
        # ambiguous which number is a count and which is a unit description.
        columns = ("item", "qty", "unit", "servings", "macros", "cost")
        tree = ttk.Treeview(table_card, columns=columns, show="headings", height=min(10, len(totals.lines)))
        headings = {"item": "Food item", "qty": "Quantity", "unit": "Unit type", "servings": "Servings",
                    "macros": "Per serving", "cost": "Total cost"}
        widths = {"item": 170, "qty": 70, "unit": 110, "servings": 80, "macros": 250, "cost": 90}
        # Long free-text columns read better left-aligned; short/numeric-ish
        # columns read better centered. Set the heading and its column's
        # values to the SAME anchor explicitly — leaving the heading anchor
        # unset let it fall back to the theme's default (center) while the
        # column values were set independently, which is what caused the
        # heading/value mismatch on "Unit type".
        anchors = {"item": "w", "qty": "center", "unit": "center", "servings": "center",
                   "macros": "w", "cost": "center"}
        for col, text in headings.items():
            tree.heading(col, text=text, anchor=anchors[col])
            tree.column(col, width=widths[col], anchor=anchors[col])
        tree.tag_configure("odd", background=ROW_ALT)
        tree.tag_configure("even", background="white")
        tree.pack(fill="x", padx=18, pady=(0, 4))
        tk.Label(table_card, text="Quantity = how many of that unit; Unit type = what one unit is (e.g. a 12oz can).",
                 font=FONT_SMALL, bg=CARD_BG, fg=MUTED).pack(anchor="w", padx=18, pady=(0, 8))

        for i, line in enumerate(sorted(totals.lines, key=lambda ln: -ln.kcal_total)):
            macros = f"{line.per_serving_kcal} kcal · {line.per_serving_protein}g P · {line.per_serving_carbs}g C · {line.per_serving_fat}g F"
            tree.insert("", "end", values=(line.item, line.qty, line.unit, line.servings_total,
                                            macros, f"${line.cost_total:,.2f}"),
                        tags=("odd" if i % 2 else "even",))

        tk.Label(table_card, text=package.source_note, font=FONT_SMALL, bg=CARD_BG, fg=MUTED).pack(
            anchor="w", padx=18, pady=(0, 14))

    def _build_snap_summary(self, balance: float):
        cards_row = tk.Frame(self.step_area, bg=BG)
        cards_row.pack(fill="x", pady=(0, 4))
        c1 = SummaryCard(cards_row, "Monthly SNAP balance")
        c1.pack(side="left", fill="both")
        c1.set(f"${balance:,.0f}/mo", f"~${per_week(balance):,.0f}/week")


# --- Recipes page (grid, tags, filtering) ------------------------------------

class FinancesPage(tk.Frame):
    """Quick, direct access to the budget — reuses the same shared
    HouseholdProfile the Calculator writes to, so setting things up in
    either place carries over to the other. If the household/program is
    already set, this jumps straight to the expense form; otherwise it
    shows a compact one-screen setup first."""

    def __init__(self, parent, controller):
        super().__init__(parent, bg=BG)
        self.controller = controller
        self._setup_expanded = False
        build_navbar(self, controller, "Finances")

        self.scroller = ScrollableFrame(self)
        self.scroller.pack(fill="both", expand=True, padx=28, pady=(8, 20))
        self.body = self.scroller.body

        self._render()

    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        self._render()  # refresh in case the profile changed on another page

    def _render(self):
        clear_frame(self.body)
        profile = self.controller.profile

        summary_row = tk.Frame(self.body, bg=BG)
        summary_row.pack(fill="x", pady=(0, 12))
        if profile.program:
            detail = (f"({profile.agency_key})" if profile.program == "FDPIR"
                       else f"(${profile.snap_balance:,.0f}/mo SNAP)")
            tk.Label(summary_row, text=f"Household of {profile.household_size} · {profile.program} {detail}",
                     font=FONT_LABEL_BOLD, bg=BG, fg=ACCENT_DARK, wraplength=600, justify="left").pack(
                side="left")
            ttk.Button(summary_row, text="Change", style="Ghost.TButton", cursor="hand2",
                       command=self._toggle_setup).pack(side="left", padx=(12, 0))
        else:
            tk.Label(summary_row, text="Set up your household once below — it's shared with the Calculator too.",
                     font=FONT_LABEL, bg=BG, fg=MUTED, wraplength=700, justify="left").pack(anchor="w")

        if profile.program is None or self._setup_expanded:
            self._build_setup_card(profile)
        else:
            program_value = self._current_program_value(profile)
            build_finances_section(self.body, profile, self.controller, program_value)
            if profile.has_school_age_children:
                build_school_meals_section(self.body, profile)

        self.body.update_idletasks()
        self.scroller.canvas.yview_moveto(0)

    def _toggle_setup(self):
        self._setup_expanded = not self._setup_expanded
        self._render()

    @staticmethod
    def _current_program_value(profile: HouseholdProfile) -> float:
        if profile.program == "FDPIR":
            package = FOOD_PACKAGES[profile.agency_key]
            return totals_for_package(package, profile.household_size).total_cost
        return profile.snap_balance

    def _build_setup_card(self, profile: HouseholdProfile):
        card = tk.Frame(self.body, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", pady=(0, 14))
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="x", padx=22, pady=20)

        tk.Label(inner, text="Household size", font=FONT_LABEL_BOLD, bg=CARD_BG, fg=TEXT).pack(anchor="w")
        hh_var = tk.IntVar(value=profile.household_size)
        ttk.Spinbox(inner, from_=1, to=12, textvariable=hh_var, width=6, font=FONT_LABEL,
                    justify="center").pack(anchor="w", pady=(6, 16))

        tk.Label(inner, text="Which food program applies to your household?", font=FONT_LABEL_BOLD,
                 bg=CARD_BG, fg=TEXT).pack(anchor="w")
        tk.Label(inner, text="A household is enrolled in FDPIR or SNAP, not both.", font=FONT_SMALL,
                 bg=CARD_BG, fg=MUTED).pack(anchor="w", pady=(2, 4))
        program_var, agency_var, snap_var = build_program_picker(inner, profile)

        tk.Label(inner, text="Monthly take-home pay", font=FONT_LABEL_BOLD, bg=CARD_BG, fg=TEXT).pack(
            anchor="w", pady=(20, 4))
        row = tk.Frame(inner, bg=CARD_BG)
        row.pack(anchor="w")
        amount_var = tk.StringVar(value=str(profile.salary_amount) if profile.salary_amount else "")
        ttk.Entry(row, textvariable=amount_var, width=14, font=FONT_LABEL).pack(side="left")
        freq_var = tk.StringVar(value=profile.salary_frequency)
        ttk.Radiobutton(row, text="Monthly", value="Monthly", variable=freq_var).pack(side="left", padx=(16, 0))
        ttk.Radiobutton(row, text="Yearly", value="Yearly", variable=freq_var).pack(side="left", padx=(8, 0))

        school_var = tk.BooleanVar(value=profile.has_school_age_children)
        ttk.Checkbutton(inner, text="We have school-age children (K-12) in the household",
                        variable=school_var).pack(anchor="w", pady=(16, 0))

        def save_and_continue():
            try:
                size = int(hh_var.get())
                if size < 1:
                    raise ValueError
            except (tk.TclError, ValueError):
                messagebox.showerror("Check household size", "Household size must be a whole number of 1 or more.")
                return
            program = program_var.get()
            if program not in ("FDPIR", "SNAP"):
                messagebox.showerror("Choose a program", "Select FDPIR or SNAP to continue.")
                return
            if program == "SNAP":
                try:
                    balance = float(snap_var.get() or 0)
                    if balance < 0:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("Check SNAP balance", "Enter a SNAP balance of 0 or more.")
                    return
                profile.snap_balance = balance
            else:
                profile.agency_key = agency_var.get()
            try:
                amount = float(amount_var.get() or 0)
                if amount < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Check income", "Enter take-home pay as a number of 0 or more.")
                return

            profile.household_size = size
            profile.program = program
            profile.salary_amount = amount
            profile.salary_frequency = freq_var.get()
            profile.has_school_age_children = school_var.get()
            self._setup_expanded = False
            self._render()

        ttk.Button(inner, text="Continue to Budget", style="Accent.TButton", cursor="hand2",
                   command=save_and_continue).pack(anchor="w", pady=(20, 0))


class RecipesPage(tk.Frame):
    CARD_COLORS = ["#5b6b3a", "#8a5a3b", "#3b6b78", "#7a4f6b"]

    def __init__(self, parent, controller):
        super().__init__(parent, bg=BG)
        self.controller = controller
        self.selected_tags: set = set()       # dietary tags that must ALL be present
        self.excluded_allergens: set = set()  # allergens that must NOT be present
        build_navbar(self, controller, "Recipes")

        note_row = tk.Frame(self, bg=BG)
        note_row.pack(fill="x", padx=28, pady=(0, 8))
        tk.Label(note_row, text="Built from common FDPIR food items — cost and nutrition are estimates.",
                 font=FONT_SMALL, bg=BG, fg=MUTED).pack(anchor="w")

        self.filter_var = tk.BooleanVar(value=True)
        self.filter_check = ttk.Checkbutton(note_row, text="Only show recipes that fit my selected FDPIR package",
                                             variable=self.filter_var, command=self._render_grid)
        # Only shown/relevant once a package has actually been selected in the Calculator.
        self.filter_check.pack(anchor="w", pady=(4, 0))

        self._build_tag_filters(note_row)

        self.scroller = ScrollableFrame(self)
        self.scroller.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        self.grid_frame = tk.Frame(self.scroller.body, bg=BG)
        # No fill/expand here: a frame with only .grid() children sizes to
        # its natural content width, so packing it with the default center
        # anchor centers the whole grid instead of stretching cards edge to
        # edge across the window.
        self.grid_frame.pack(pady=4)
        self.GRID_COLUMNS = 3
        for col in range(self.GRID_COLUMNS):
            self.grid_frame.grid_columnconfigure(col, weight=0)

        self._render_grid()

    def _build_tag_filters(self, parent):
        self.tag_chips: Dict[str, ToggleChip] = {}
        self.allergen_chips: Dict[str, ToggleChip] = {}

        if ALL_DIETARY_TAGS:
            row = tk.Frame(parent, bg=BG)
            row.pack(anchor="w", pady=(10, 2), fill="x")
            tk.Label(row, text="Dietary preference:", font=FONT_SMALL, bg=BG, fg=MUTED).pack(side="left", padx=(0, 6))
            for tag in ALL_DIETARY_TAGS:
                chip = ToggleChip(row, tag, ACCENT, on_toggle=lambda active, t=tag: self._toggle_tag(t, active))
                chip.pack(side="left", padx=(0, 4))
                self.tag_chips[tag] = chip

        if ALL_ALLERGENS:
            row2 = tk.Frame(parent, bg=BG)
            row2.pack(anchor="w", pady=(6, 2), fill="x")
            tk.Label(row2, text="Avoid:", font=FONT_SMALL, bg=BG, fg=MUTED).pack(side="left", padx=(0, 6))
            for tag in ALL_ALLERGENS:
                chip = ToggleChip(row2, tag, WARN, on_toggle=lambda active, t=tag: self._toggle_allergen(t, active))
                chip.pack(side="left", padx=(0, 4))
                self.allergen_chips[tag] = chip

    def _toggle_tag(self, tag: str, active: bool):
        if active:
            self.selected_tags.add(tag)
        else:
            self.selected_tags.discard(tag)
        self._render_grid()

    def _toggle_allergen(self, tag: str, active: bool):
        if active:
            self.excluded_allergens.add(tag)
        else:
            self.excluded_allergens.discard(tag)
        self._render_grid()

    def _selected_package(self) -> Optional[FDPIRPackage]:
        profile = self.controller.profile
        if profile.program == "FDPIR" and profile.agency_key:
            return FOOD_PACKAGES.get(profile.agency_key)
        return None

    def tkraise(self, *args, **kwargs):
        # Refresh the filter checkbox's relevance and the grid each time this
        # page is shown, in case the Calculator selection changed since.
        super().tkraise(*args, **kwargs)
        package = self._selected_package()
        if package is None:
            self.filter_check.pack_forget()
        else:
            self.filter_check.pack(anchor="w", pady=(4, 0))
        self._render_grid()

    def _clear_all_filters(self):
        self.filter_var.set(False)
        self.selected_tags.clear()
        self.excluded_allergens.clear()
        for chip in list(self.tag_chips.values()) + list(self.allergen_chips.values()):
            chip.is_active = False
            chip._apply_style()
        self._render_grid()

    def _render_grid(self):
        clear_frame(self.grid_frame)
        package = self._selected_package()
        show_filtered = package is not None and self.filter_var.get()

        recipes_to_show = RECIPES
        if show_filtered:
            recipes_to_show = [r for r in recipes_to_show if recipe_fits_package(r, package)]
        if self.selected_tags:
            recipes_to_show = [r for r in recipes_to_show if self.selected_tags.issubset(set(r.best_for))]
        if self.excluded_allergens:
            recipes_to_show = [r for r in recipes_to_show if not (self.excluded_allergens & set(r.allergens))]

        if not recipes_to_show:
            tk.Label(self.grid_frame, text="No recipes match the current filters.",
                     font=FONT_LABEL, bg=BG, fg=MUTED, wraplength=700,
                     justify="left").grid(row=0, column=0, columnspan=self.GRID_COLUMNS, sticky="w", pady=(10, 6))
            ttk.Button(self.grid_frame, text="Clear all filters", style="Accent.TButton", cursor="hand2",
                       command=self._clear_all_filters).grid(row=1, column=0, columnspan=self.GRID_COLUMNS,
                                                              sticky="w", pady=(0, 10))
            return

        for i, recipe in enumerate(recipes_to_show):
            self._build_card(self.grid_frame, recipe, self.CARD_COLORS[i % len(self.CARD_COLORS)], package).grid(
                row=i // self.GRID_COLUMNS, column=i % self.GRID_COLUMNS, sticky="n", padx=8, pady=8)

    CARD_WIDTH = 300
    # Measured worst case across every recipe/package combo (a long
    # missing-ingredients line plus several tag chips) is ~348px; this adds
    # some margin. A fixed height is required alongside pack_propagate(False)
    # below — disabling propagation with only a width set (no height) was
    # the actual bug: the frame collapsed to ~1px since nothing told it how
    # tall to be, silently clipping every child inside it to invisible.
    CARD_HEIGHT = 380

    def _build_card(self, parent, recipe: Recipe, accent: str, package: Optional[FDPIRPackage]) -> tk.Frame:
        totals = compute_recipe_totals(recipe)
        cost_ps, kcal_ps, protein_ps, _, _ = totals.per_serving(recipe.yields_servings)

        outer = tk.Frame(parent, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1,
                          width=self.CARD_WIDTH, height=self.CARD_HEIGHT)
        outer.pack_propagate(False)  # lock the outer box's size; content below just fills it
        card = tk.Frame(outer, bg=CARD_BG)
        card.pack(fill="both", expand=True)

        tk.Frame(card, bg=accent, height=6).pack(fill="x")
        tk.Label(card, text=recipe.name, font=FONT_LABEL_BOLD, bg=CARD_BG, fg=TEXT,
                 wraplength=self.CARD_WIDTH - 32, justify="left").pack(anchor="w", padx=16, pady=(12, 2))
        tk.Label(card, text=recipe.description, font=FONT_LABEL, bg=CARD_BG, fg=MUTED,
                 wraplength=self.CARD_WIDTH - 32, justify="left").pack(anchor="w", padx=16)
        tk.Label(card, text=f"~${cost_ps:,.2f}/serving · {kcal_ps:,.0f} kcal · {protein_ps:,.0f}g protein · "
                             f"serves {recipe.yields_servings}",
                 font=FONT_SMALL, bg=CARD_BG, fg=MUTED, wraplength=self.CARD_WIDTH - 32,
                 justify="left").pack(anchor="w", padx=16, pady=(6, 8))

        if package is not None:
            missing = missing_ingredients(recipe, package)
            if missing:
                tk.Label(card, text=f"Missing from your package: {', '.join(missing)} — substitute if needed.",
                         font=FONT_SMALL, bg=CARD_BG, fg=WARN, wraplength=self.CARD_WIDTH - 32,
                         justify="left").pack(anchor="w", padx=16, pady=(0, 8))

        chip_row = tk.Frame(card, bg=CARD_BG)
        chip_row.pack(anchor="w", padx=16, pady=(0, 8), fill="x")
        for tag in recipe.best_for:
            make_chip(chip_row, tag, ACCENT).pack(side="left", padx=(0, 4), pady=2)
        for tag in recipe.allergens:
            make_chip(chip_row, f"Contains {tag}", WARN).pack(side="left", padx=(0, 4), pady=2)

        ttk.Button(card, text="View recipe", style="Ghost.TButton", cursor="hand2",
                   command=lambda r=recipe: self._open_detail(r, package)).pack(anchor="w", padx=16, pady=(4, 14))
        return outer

    def _open_detail(self, recipe: Recipe, package: Optional[FDPIRPackage] = None):
        totals = compute_recipe_totals(recipe)
        cost_ps, kcal_ps, protein_ps, carbs_ps, fat_ps = totals.per_serving(recipe.yields_servings)
        missing = missing_ingredients(recipe, package) if package is not None else []

        win = tk.Toplevel(self)
        win.title(recipe.name)
        # A new Toplevel can silently open behind the main window on some
        # platforms/window managers without this — which looks exactly like
        # "clicking did nothing."
        win.transient(self.winfo_toplevel())
        win.lift()
        win.after(10, win.lift)
        win.focus_force()
        win.configure(bg=BG)
        win.geometry("640x680")

        scroller = ScrollableFrame(win)
        scroller.pack(fill="both", expand=True, padx=20, pady=20)
        body = scroller.body

        tk.Label(body, text=recipe.name, font=FONT_RECIPE_TITLE, bg=BG, fg=TEXT).pack(anchor="w")
        tk.Label(body, text=recipe.description, font=FONT_SUB, bg=BG, fg=MUTED, wraplength=580,
                 justify="left").pack(anchor="w", pady=(4, 10))

        if missing:
            tk.Label(body, text=f"Missing from your selected package: {', '.join(missing)}. Everything else "
                                 f"below is in your package — swap in what you have for the missing item(s).",
                     font=FONT_LABEL, bg=BG, fg=WARN, wraplength=580, justify="left").pack(anchor="w", pady=(0, 10))

        if recipe.best_for or recipe.allergens:
            chip_row = tk.Frame(body, bg=BG)
            chip_row.pack(anchor="w", pady=(0, 12))
            for tag in recipe.best_for:
                make_chip(chip_row, tag, ACCENT).pack(side="left", padx=(0, 4))
            for tag in recipe.allergens:
                make_chip(chip_row, f"Contains {tag}", WARN).pack(side="left", padx=(0, 4))

        stats = tk.Frame(body, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1)
        stats.pack(fill="x", pady=(0, 14))
        tk.Label(stats, text=f"Serves {recipe.yields_servings}", font=FONT_LABEL_BOLD, bg=CARD_BG, fg=TEXT).pack(
            anchor="w", padx=16, pady=(12, 2))
        tk.Label(stats, text=f"${cost_ps:,.2f} per serving  (${totals.cost_total:,.2f} total)",
                 font=FONT_LABEL, bg=CARD_BG, fg=TEXT).pack(anchor="w", padx=16)
        tk.Label(stats, text=f"{kcal_ps:,.0f} kcal · {protein_ps:,.0f}g protein · {carbs_ps:,.0f}g carbs · "
                              f"{fat_ps:,.0f}g fat — per serving",
                 font=FONT_LABEL, bg=CARD_BG, fg=TEXT).pack(anchor="w", padx=16, pady=(0, 12))

        tk.Label(body, text="Ingredients", font=FONT_LABEL_BOLD, bg=BG, fg=TEXT).pack(anchor="w", pady=(4, 4))
        for ing in recipe.ingredients:
            tk.Label(body, text=f"• {ing.servings_used:g} serving(s) of {ing.item_name}", font=FONT_LABEL,
                     bg=BG, fg=TEXT).pack(anchor="w")

        tk.Label(body, text="Steps", font=FONT_LABEL_BOLD, bg=BG, fg=TEXT).pack(anchor="w", pady=(14, 4))
        for i, step in enumerate(recipe.steps, start=1):
            tk.Label(body, text=f"{i}. {step}", font=FONT_LABEL, bg=BG, fg=TEXT, wraplength=580,
                     justify="left").pack(anchor="w", pady=(0, 6))


# --- Locator page (with gas-cost estimate) -----------------------------------

class LocatorPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=BG)
        self.controller = controller
        build_navbar(self, controller, "Locator")

        form_card = tk.Frame(self, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1)
        form_card.pack(fill="x", padx=28, pady=(4, 12))
        inner = tk.Frame(form_card, bg=CARD_BG)
        inner.pack(fill="x", padx=22, pady=18)

        tk.Label(inner, text="Enter your ZIP code", font=FONT_LABEL_BOLD, bg=CARD_BG, fg=TEXT).pack(anchor="w")
        tk.Label(inner, text="Distances shown are straight-line estimates, not driving directions.",
                 font=FONT_SMALL, bg=CARD_BG, fg=MUTED).pack(anchor="w", pady=(2, 10))

        row = tk.Frame(inner, bg=CARD_BG)
        row.pack(anchor="w")
        self.zip_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.zip_var, width=10, font=FONT_LABEL)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self._search())
        ttk.Button(row, text="Find Nearest Center", style="Accent.TButton", cursor="hand2",
                   command=self._search).pack(side="left", padx=(12, 0))

        demo_zips = ", ".join(sorted(ZIP_COORDINATES.keys()))
        tk.Label(inner, text=f"This offline demo only has a small sample of ZIP codes bundled: {demo_zips}",
                 font=FONT_SMALL, bg=CARD_BG, fg=MUTED, wraplength=760, justify="left").pack(anchor="w", pady=(10, 0))

        self.results_scroller = ScrollableFrame(self)
        self.results_scroller.pack(fill="both", expand=True, padx=28, pady=(0, 20))

    def _search(self):
        clear_frame(self.results_scroller.body)
        zip_code = self.zip_var.get().strip()
        results = find_nearest_sites(zip_code)

        if results is None:
            tk.Label(self.results_scroller.body,
                     text=f"\"{zip_code}\" isn't in this offline demo's small ZIP sample. "
                          f"Try one of the ZIP codes listed above.",
                     font=FONT_LABEL, bg=BG, fg=WARN, wraplength=760, justify="left").pack(anchor="w", pady=10)
            return

        for rank, (site, distance) in enumerate(results, start=1):
            card = tk.Frame(self.results_scroller.body, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1)
            card.pack(fill="x", pady=6)
            tk.Label(card, text=f"#{rank} · {site.agency}", font=FONT_LABEL_BOLD, bg=CARD_BG, fg=ACCENT_DARK).pack(
                anchor="w", padx=16, pady=(12, 2))
            tk.Label(card, text=f"~{distance:,.0f} miles (straight-line estimate)", font=FONT_LABEL,
                     bg=CARD_BG, fg=TEXT).pack(anchor="w", padx=16)
            tk.Label(card, text=site.address, font=FONT_LABEL, bg=CARD_BG, fg=TEXT, wraplength=700,
                     justify="left").pack(anchor="w", padx=16, pady=(4, 0))
            tk.Label(card, text=f"{site.phone} · {site.hours}", font=FONT_SMALL, bg=CARD_BG, fg=MUTED).pack(
                anchor="w", padx=16, pady=(2, 8))

            self._build_actions_row(card, site)

            if rank == 1:
                self._build_gas_cost_row(card, distance)

    def _build_actions_row(self, parent, site: FDPIRSite):
        row = tk.Frame(parent, bg=CARD_BG)
        row.pack(anchor="w", padx=16, pady=(0, 10))

        status_lbl = tk.Label(row, text="", font=FONT_SMALL, bg=CARD_BG, fg=ACCENT_DARK)

        def use_as_agency():
            self.controller.profile.program = "FDPIR"
            self.controller.profile.agency_key = site.agency
            status_lbl.config(text=f"Set as your FDPIR agency — the Calculator and Finances pages will use it.")
            status_lbl.pack(anchor="w", pady=(6, 0))

        ttk.Button(row, text="Use as my FDPIR agency", style="Ghost.TButton", cursor="hand2",
                   command=use_as_agency).pack(side="left")

        maps_url = f"https://www.google.com/maps/search/?api=1&query={site.lat},{site.lon}"

        def open_maps():
            try:
                webbrowser.open(maps_url)
            except Exception:
                pass  # opportunistic only — offline or no browser is a silent no-op, not an error

        ttk.Button(row, text="Open in Maps", style="Ghost.TButton", cursor="hand2",
                   command=open_maps).pack(side="left", padx=(8, 0))
        tk.Label(row, text="(needs a connection)", font=FONT_SMALL, bg=CARD_BG, fg=MUTED).pack(side="left", padx=(4, 0))

    def _build_gas_cost_row(self, parent, one_way_miles: float):
        row = tk.Frame(parent, bg=ACCENT_LIGHT)
        row.pack(fill="x", padx=16, pady=(0, 14))
        inner = tk.Frame(row, bg=ACCENT_LIGHT)
        inner.pack(fill="x", padx=12, pady=10)

        tk.Label(inner, text="Estimate the gas cost of getting here", font=FONT_LABEL_BOLD,
                 bg=ACCENT_LIGHT, fg=ACCENT_DARK).pack(anchor="w")
        tk.Label(inner, text=f"Assumes ~{ASSUMED_MPG} mpg at ${GAS_PRICE_PER_GALLON:.2f}/gallon "
                              f"(U.S. DOT national average, August 2026).",
                 font=FONT_SMALL, bg=ACCENT_LIGHT, fg=MUTED, wraplength=700, justify="left").pack(anchor="w", pady=(2, 8))

        trip_row = tk.Frame(inner, bg=ACCENT_LIGHT)
        trip_row.pack(anchor="w")
        tk.Label(trip_row, text="Trips per month:", font=FONT_LABEL, bg=ACCENT_LIGHT, fg=TEXT).pack(side="left")
        trips_var = tk.StringVar(value="1")
        ttk.Entry(trip_row, textvariable=trips_var, width=6, font=FONT_LABEL).pack(side="left", padx=(8, 12))

        result_lbl = tk.Label(inner, text="", font=FONT_LABEL_BOLD, bg=ACCENT_LIGHT, fg=ACCENT_DARK)
        result_lbl.pack(anchor="w", pady=(8, 0))

        def compute_and_show():
            try:
                trips = float(trips_var.get() or 0)
                if trips < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Check trips per month", "Enter a number of 0 or more.")
                return
            monthly_cost = estimate_monthly_gas_cost(one_way_miles * 2, trips)
            self.controller.shared_gas_cost = monthly_cost
            result_lbl.config(text=f"≈ ${monthly_cost:,.0f}/month — added to the Calculator's Finances step "
                                    f"as \"Travel to distribution site\" (edit it there if you'd like).")

        ttk.Button(trip_row, text="Add to my budget", style="Accent.TButton", cursor="hand2",
                   command=compute_and_show).pack(side="left")


# --- About page -----------------------------------------------------------

class AboutPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=BG)
        build_navbar(self, controller, "About")

        scroller = ScrollableFrame(self)
        scroller.pack(fill="both", expand=True, padx=28, pady=(4, 20))

        for heading, body in LEARN_SECTIONS:
            section = tk.Frame(scroller.body, bg=BG)
            section.pack(fill="x", pady=(0, 18), padx=(2, 18))
            tk.Label(section, text=heading, font=FONT_ABOUT_HEAD, bg=BG, fg=ACCENT_DARK).pack(anchor="w")
            tk.Label(section, text=body, font=FONT_SUB, bg=BG, fg=TEXT, wraplength=820, justify="left").pack(
                anchor="w", pady=(5, 0))


# --- App root / router ------------------------------------------------------

class Sidebar(tk.Frame):
    """Persistent left navigation, visible on every page, so switching
    sections doesn't require returning to the main menu first."""
    WIDTH = 180
    ITEMS = [("MainMenu", "Home"), ("Calculator", "Calculator"), ("Finances", "Finances"),
             ("Recipes", "Recipes"), ("Locator", "Locator"), ("About", "About")]

    def __init__(self, parent, controller):
        super().__init__(parent, bg=CARD_BG, width=self.WIDTH, highlightbackground=BORDER, highlightthickness=1)
        self.pack_propagate(False)  # safe here: parent packs this with fill="y", so height comes
        self.controller = controller                                      # from the parent, not from children
        self.buttons: Dict[str, tk.Label] = {}

        tk.Label(self, text="Food\nNavigator", font=FONT_MENU_TITLE, bg=CARD_BG, fg=TEXT,
                 justify="left").pack(anchor="w", padx=16, pady=(20, 22))

        for name, label in self.ITEMS:
            btn = tk.Label(self, text=label, font=FONT_LABEL_BOLD, bg=CARD_BG, fg=MUTED,
                           cursor="hand2", anchor="w", padx=16, pady=9)
            btn.pack(fill="x")
            btn.bind("<Button-1>", lambda e, n=name: self.controller.show_frame(n))
            btn.bind("<Enter>", lambda e, n=name: self._on_enter(n))
            btn.bind("<Leave>", lambda e, n=name: self._on_leave(n))
            self.buttons[name] = btn

    def _on_enter(self, name: str):
        if name != self.controller.current_page:
            self.buttons[name].configure(bg=ACCENT_LIGHT)

    def _on_leave(self, name: str):
        if name != self.controller.current_page:
            self.buttons[name].configure(bg=CARD_BG)

    def set_active(self, name: str):
        for n, btn in self.buttons.items():
            if n == name:
                btn.configure(bg=ACCENT, fg="white")
            else:
                btn.configure(bg=CARD_BG, fg=MUTED)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GroundTruth — the Household Food Navigator")
        self.geometry("1140x800")
        self.configure(bg=BG)
        self.minsize(960, 700)

        # Fonts must exist (as live Font objects, not tuples) before
        # configure_styles or any page is built, since both reference these
        # names directly — and this is also what makes the text-size
        # control below able to rescale everything without rebuilding it.
        init_fonts(self)

        # Shared, in-memory-only state that lets sections hand data to each
        # other while the app is open (household/program/income feeding the
        # Calculator and Finances page alike; Locator's gas estimate feeding
        # the budget). Nothing here is ever written to disk, so it's gone
        # the moment the app closes — there is nothing to clear.
        self.profile = HouseholdProfile()
        self.shared_gas_cost: Optional[float] = None
        self.last_budget: Optional[BudgetResult] = None  # feeds the main-menu status strip
        self.current_page = "MainMenu"

        configure_styles(self)
        tk.Frame(self, bg=ACCENT, height=6).pack(fill="x", side="top")
        self._build_text_size_control()

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        self.sidebar = Sidebar(body, self)
        self.sidebar.pack(side="left", fill="y")

        container = tk.Frame(body, bg=BG)
        container.pack(side="left", fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.frames: Dict[str, tk.Frame] = {}
        for name, cls in [("MainMenu", MainMenuPage), ("Calculator", CalculatorPage), ("Finances", FinancesPage),
                           ("Recipes", RecipesPage), ("Locator", LocatorPage), ("About", AboutPage)]:
            frame = cls(container, self)
            self.frames[name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        # Surface any unhandled error in a dialog instead of letting it print
        # to a console the person may not have (e.g. launched by double-click
        # on Windows) — without this, a failed action can look like "nothing
        # happened" rather than a visible, fixable error.
        self.report_callback_exception = self._show_error_dialog

        self.show_frame("MainMenu")

    def _build_text_size_control(self):
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", side="top")
        tk.Label(bar, text="Text size:", font=FONT_SMALL, bg=BG, fg=MUTED).pack(side="right", pady=4)
        ttk.Button(bar, text="A+", style="Ghost.TButton", width=3, cursor="hand2",
                   command=lambda: self._adjust_font_scale(0.1)).pack(side="right", padx=(4, 8))
        ttk.Button(bar, text="Reset", style="Ghost.TButton", cursor="hand2",
                   command=lambda: self._adjust_font_scale(None)).pack(side="right", padx=4)
        ttk.Button(bar, text="A−", style="Ghost.TButton", width=3, cursor="hand2",
                   command=lambda: self._adjust_font_scale(-0.1)).pack(side="right", padx=(8, 4))

    def _adjust_font_scale(self, delta: Optional[float]):
        set_font_scale(1.0 if delta is None else get_font_scale() + delta)

    def _show_error_dialog(self, exc, val, tb):
        detail = "".join(traceback.format_exception(exc, val, tb))[-1500:]
        messagebox.showerror("Something went wrong", f"{val}\n\nDetails:\n{detail}")

    def show_frame(self, name: str):
        self.current_page = name
        self.sidebar.set_active(name)
        self.frames[name].tkraise()


if __name__ == "__main__":
    app = App()
    app.mainloop()
