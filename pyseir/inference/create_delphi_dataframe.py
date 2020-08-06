import math
import us
from datetime import datetime, timedelta
import numpy as np
import logging
import pandas as pd
import os, sys, glob
from matplotlib import pyplot as plt
import us
import structlog
from functools import reduce
import os, sys

# import covidcast
# data2 = covidcast.signal("safegraph","full_time_work_prop", None, None, "state")
# data2 = covidcast.signal("safegraph","part_time_work_prop", None, None, "state")

CSV_FOLDER = "/Users/natashawoods/Desktop/later.nosync/covid_act_now.nosync/covid-data-public/data/aws-lake/using/"
aggregate_level_name = "aggregate_level"
aggregate_select = "state"

# load CAN input data
# can_data = "/Users/natashawoods/Desktop/later.nosync/covid_act_now.nosync/covid-data-model/pyseir_data/merged_results.csv"
can_data = "/Users/natashawoods/Desktop/covid-data-model/data/timeseries.csv"
can_df = pd.read_csv(can_data, converters={"fips": str}, parse_dates=True, index_col="date")


# Delphi Data
delphi_dataframes = []
# Mobility data that we don't currently cache
full_time_safegraph = "/Users/natashawoods/Desktop/later.nosync/covid_act_now.nosync/covid-data-model/pyseir_data/state_full_time_work_prop.csv"
part_time_safegraph = "/Users/natashawoods/Desktop/later.nosync/covid_act_now.nosync/covid-data-model/pyseir_data/state_part_time_work_prop.csv"

full_df = pd.read_csv(full_time_safegraph, parse_dates=True)
full_df["fips"] = full_df.apply(lambda x: us.states.lookup(x["geo_value"]).fips, axis=1)
full_df.rename(columns={"time_value": "date", "value": "full_mobility"}, inplace=True)
full_df["aggregate_level"] = "state"
full_df["state"] = full_df.apply(lambda x: x["geo_value"].upper(), axis=1)
full_df.to_csv("full_mobility.csv")
os.system(f"mv full_mobility.csv {CSV_FOLDER}")
# full_df.index = full_df['date']
print(full_df.columns)
print(full_df.head())
# full_df.drop('date', inplace = True)


part_df = pd.read_csv(part_time_safegraph, parse_dates=True)
part_df["fips"] = part_df.apply(lambda x: us.states.lookup(x["geo_value"]).fips, axis=1)
part_df.rename(columns={"time_value": "date", "value": "part_mobility"}, inplace=True)
part_df["aggregate_level"] = "state"
part_df["state"] = part_df.apply(lambda x: x["geo_value"].upper(), axis=1)
part_df.to_csv("part_mobility.csv")
part_df.to_csv("part_mobility.csv")
os.system(f"mv part_mobility.csv {CSV_FOLDER}")
# part_df.index = part_df['date']
# part_df.drop('date', inplace = True)


print(full_df.head())

# delphi_dataframes.append(full_df)
# delphi_dataframes.append(part_df)

# Get list of all available CSV files
csv_files = glob.glob(CSV_FOLDER + "*csv")
print(csv_files)


for delphi_file in csv_files:
    print(delphi_file)
    delphi_var_df = pd.read_csv(
        delphi_file, converters={"fips": str}, parse_dates=True, index_col="date"
    )

    delphi_var_df = delphi_var_df[delphi_var_df[aggregate_level_name] == aggregate_select]

    delphi_dataframes.append(delphi_var_df)
    print(delphi_var_df.columns)

merged_df = reduce(
    lambda left, right: pd.merge(
        left,
        right,
        left_on=["fips", "date", aggregate_level_name, aggregate_select],
        right_on=["fips", "date", aggregate_level_name, aggregate_select],
    ),
    delphi_dataframes,
)

merged_df.to_csv("merged_delphi_df.csv")
# Merge dataframes
final_merged_df = pd.merge(
    can_df,
    merged_df,
    how="left",
    left_on=["fips", "date", aggregate_level_name, aggregate_select],
    right_on=["fips", "date", aggregate_level_name, aggregate_select],
)

final_merged_df.to_csv("merged_delphi_df.csv")

# merged_df["fips_int"] = merged_df["fips"].astype(int)
# merged_df.to_csv("delphi_merged.csv")
