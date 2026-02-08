# PowstonAutoTuned: Decision Script
min_soc = 18  # % Minimum battery SOC
action = decisions.reason('auto', 'Starting in auto mode - default', buy_price=buy_price, sell_price=sell_price)
c_rating = 4  # number of half hours to charge/discharge
peak_hour_start = 16  # noqa
BATTERY_SOC_AC = 20  # noqa
soaker_hour_start = 11  # noqa
# Pricing Decisions - ALL CAPS variables are tuned by machine learning
GOOD_SUN_DAY = 32
BATTERY_SOC_NEEDED = 18  # noqa
GOOD_SUN_HOUR = 6  # noqa
BAD_SUN_DAY_KEEP_SOC = 33  # noqa
ALWAYS_IMPORT_SOC = 4  # The battery SOC at which we always import
DEFAULT_EXPORT = 100

# PowstonBlock

# Custom code

# Disable curtailment as Flow does not charge for negative exports with the happy hour plan
# We need to know how much solar is going to waste once battery is full before 5:30pm
# so we can optimize charging strategy to minimise daily grid import
# If we curtail then Elekeeper will not be able to record how much extra solar
# is produced after battery is full
feed_in_power_limitation = None

# interval_time is the timstamp of the end of an trading interval (NOT the beginning)
i_hour = interval_time.hour
i_minute = interval_time.minute

# NOTE this import logic below is just to suppliment Poweston Magic mode - 
# the idea is that becasue we are blocking <11am and >2pm imports, Powston may 
# not have the opportunity to do all the importing it wanted to so we need to do
# some more during the 11am to 2pm period.
#
# Once Powston starts receiving the real Flow live pricing feed the below should 
# not be requried anymore
#
# Crude prediction of whether solar will be enough to fill battery+supply house:
# the solar production peaks at about 1pm AEDT (according to Elekeeper in Jan), 
# so by 1pm we expect battery to be 50% full. Crude linear modelling based on this:
#
# expected SoC gain per hour: 16% (8kwh of a 45kWh usable battery)
# 
# Below model is based on the funny Flow AEST offset (they know its a mistake) 
# "11am to 3pm" solar soak period
# <time> = <soc>
# 11am = 16%
# 12pm = 32%
# 1pm = 48%
# 2pm = 64%
# 3pm = 80%
# 4pm = 96%
#
# below modelling based on real AEMO+Endeavour N71 solar soak times
# <time> = <soc>
# 10am = 10%
# 11am = 26%
# 12pm = 42%
# 1pm = 58%
# 2pm = 74%
# 3pm = 90%
FLOW_SOLAR_SOAK_START_HOUR = 11  # Flow "AEST" N71 solar soak start hour (accounting for their DST mistake)
FLOW_SOLAR_SOAK_END_HOUR = 15  # Flow "AEST" N71 solar soak end hour (accounting for their DST mistake)

# 15c/kWh = 45c Flow happy hour sell rate - 20c Flow AVG post PEA buy rate - 10c target min profit margin
MAX_BUY_PRICE = 15

TARGET_START_HOUR_SOC = 16
TARGET_SOC_GAIN_PER_HOUR = 16
TARGET_SOC_GAIN_PER_MINUTE = TARGET_SOC_GAIN_PER_HOUR/60
CHEAP_BUY_PRICE = 5  # 7 is roughly 3c/kWh wholesale + N71 solar soak period tariff
CHEAP_BUY_TARGET_SOC_OFFSET = 10  # increase the target soc if buy price is low to avoid importing at higher prices later
FLOW_PROFIT_MARGIN = 15  # a guestimate of how much Flow makes c/kWh based on historical bills
SOLAR_SOAK_DNSP_FEE = 4  # 2025-2026 FY Endeavour N71 solar soak tariff for 10am to 2pm
OFF_PEAK_DNSP_FEE = 12  # 2025-2026 FY Endeavour N71 off peak tariff 8pm-10am and 2pm-4pm LOCAL time
FLOW_OFF_PEAK_END_HOUR = 16  # Funny Flow N71 AEST off peak end hour is actually 5pm but just use 4pm to be safe
IMPORT_SOC_LIMIT = 95

# If it's a 'post Flow PEA' negative price, let magic mode import, otherwise don't import if we have enough for house loads
if action == 'import' and buy_price >= -FLOW_PROFIT_MARGIN:
    if battery_soc > 50:  
        action = decisions.reason('auto', f"No magic import when price > -{FLOW_PROFIT_MARGIN}c and soc > 50%", priority=3)
    elif buy_price > CHEAP_BUY_PRICE:
        action = decisions.reason('auto', f"No magic import when price > {CHEAP_BUY_PRICE}c", priority=3)
    elif buy_price > MAX_BUY_PRICE or battery_soc > BATTERY_SOC_AC:
        action = decisions.reason('auto', f"No magic import when price > {MAX_BUY_PRICE}c or enough soc to last until {FLOW_SOLAR_SOAK_START_HOUR}am", 
                                  priority=3, required_soc=BATTERY_SOC_AC)

if action == 'export':
    action = decisions.reason('auto', "Don't export outside of specific time periods as Flow sell=0c", priority=3)
    
if action == 'discharge' or action == 'charge':
    action = decisions.reason('auto', "Only allow auto, import and export modes", priority=3)
    
# Don't import in the morning before the funny Flow AEST solar soak period of 11am to 3pm (during Sydney daylight savings months)
if action != 'import' and FLOW_SOLAR_SOAK_START_HOUR <= i_hour < FLOW_OFF_PEAK_END_HOUR:
    gain_from_hours = (i_hour - FLOW_SOLAR_SOAK_START_HOUR) * TARGET_SOC_GAIN_PER_HOUR
    gain_from_minutes_of_current_hour = i_minute * TARGET_SOC_GAIN_PER_MINUTE
    target_soc = min(round(TARGET_START_HOUR_SOC + gain_from_hours + gain_from_minutes_of_current_hour, 2), IMPORT_SOC_LIMIT)
    dnsp_fee = OFF_PEAK_DNSP_FEE
    if i_hour < FLOW_SOLAR_SOAK_END_HOUR:
        dnsp_fee = SOLAR_SOAK_DNSP_FEE
    real_buy_price = (rrp/10) + dnsp_fee
    FLOW_SOAK_START_TEXT = f"Flow N71 AEST solar soak starts {FLOW_SOLAR_SOAK_START_HOUR}am"
    if battery_soc < target_soc and real_buy_price <= MAX_BUY_PRICE:
        action = decisions.reason('import', f"{FLOW_SOAK_START_TEXT}, {target_soc=}, {real_buy_price=}", priority=4)
    elif battery_soc < target_soc + CHEAP_BUY_TARGET_SOC_OFFSET and real_buy_price <= CHEAP_BUY_PRICE and i_hour < FLOW_SOLAR_SOAK_END_HOUR:
        reason_description = f"{FLOW_SOAK_START_TEXT} with {CHEAP_BUY_TARGET_SOC_OFFSET}% higher target SoC due to low buy price, {target_soc=}"
        action = decisions.reason('import', reason_description, priority=4, target_soc=target_soc, 
                                  low_price_target_soc_offset=CHEAP_BUY_TARGET_SOC_OFFSET, real_buy_price=real_buy_price)

if battery_soc > min_soc and action != 'export':
    if (i_hour == 17 and i_minute > 30) or i_hour == 18 or (i_hour == 19 and i_minute <= 30):
        action = decisions.reason('export', 'Flow Home FY26 plan: 45c/kWh fixed sell rate between 5:30pm and 7:30pm', priority=5)
