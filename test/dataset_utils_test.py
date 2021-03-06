import numbers
from io import StringIO
from typing import Mapping, List

import pandas as pd
import numpy as np

from covidactnow.datapublic.common_fields import COMMON_FIELDS_TIMESERIES_KEYS, CommonFields
from libs.datasets import dataset_utils
from libs.datasets.combined_datasets import _build_data_and_provenance, Override
from libs.datasets.dataset_utils import AggregationLevel
import pytest


# turns all warnings into errors for this module

pytestmark = pytest.mark.filterwarnings("error")


class NoNanDict(dict):
    """A dict that ignores None and nan values passed to __new__ and recursively creates NoNanDict for dict values."""

    # Inspired by https://stackoverflow.com/a/59685000/341400
    @staticmethod
    def is_nan(v):
        if v is None:
            return True
        if not isinstance(v, numbers.Number):
            return False
        return np.isnan(v)

    @staticmethod
    def make_value(v):
        if isinstance(v, Mapping):
            return NoNanDict(v.items())
        else:
            return v

    def __new__(cls, a):
        # Recursively apply creation of value as a NoNanDict because pandas to_dict doesn't do it for you.
        return {k: NoNanDict.make_value(v) for k, v in a if not NoNanDict.is_nan(v)}


def to_dict(keys: List[str], df: pd.DataFrame):
    """Transforms df into a dict mapping columns `keys` to a dict of the record/row in df.

    Use this to extract the values from a DataFrame for easier comparisons in assert statements.
    """
    try:
        if any(df.index.names):
            df = df.reset_index()
        df = df.set_index(keys)
        return df.to_dict(orient="index", into=NoNanDict)
    except Exception:
        # Print df to provide more context when the above code raises.
        print(f"Exception in to_dict with\n{df}")
        raise


def read_csv_and_index_fips(csv_str: str) -> pd.DataFrame:
    """Read a CSV in a str to a DataFrame and set the FIPS column as an index."""
    return pd.read_csv(
        StringIO(csv_str), dtype={CommonFields.FIPS: str}, low_memory=False,
    ).set_index(CommonFields.FIPS)


def read_csv_and_index_fips_date(csv_str: str) -> pd.DataFrame:
    """Read a CSV in a str to a DataFrame and set the FIPS and DATE columns as MultiIndex."""
    return pd.read_csv(
        StringIO(csv_str),
        parse_dates=[CommonFields.DATE],
        dtype={CommonFields.FIPS: str},
        low_memory=False,
    ).set_index(COMMON_FIELDS_TIMESERIES_KEYS)


def test_fill_fields_and_timeseries_from_column():
    # Timeseries in existing_df and new_df are merged together.
    existing_df = read_csv_and_index_fips_date(
        "fips,state,aggregate_level,county,cnt,date,foo\n"
        "55005,ZZ,county,North County,1,2020-05-01,ab\n"
        "55005,ZZ,county,North County,2,2020-05-02,cd\n"
        "55005,ZZ,county,North County,,2020-05-03,ef\n"
        "55006,ZZ,county,South County,4,2020-05-04,gh\n"
        "55,ZZ,state,Grand State,41,2020-05-01,ij\n"
        "55,ZZ,state,Grand State,43,2020-05-03,kl\n"
    )
    new_df = read_csv_and_index_fips_date(
        "fips,state,aggregate_level,county,cnt,date\n"
        "55006,ZZ,county,South County,44,2020-05-04\n"
        "55007,ZZ,county,West County,28,2020-05-03\n"
        "55005,ZZ,county,North County,3,2020-05-03\n"
        "55,ZZ,state,Grand State,42,2020-05-02\n"
    )

    datasets = {"existing": existing_df, "new": new_df}

    result, _ = _build_data_and_provenance(
        {"cnt": ["existing", "new"], "foo": ["existing"]}, datasets, Override.BY_TIMESERIES
    )

    expected = read_csv_and_index_fips_date(
        "fips,state,aggregate_level,county,cnt,date,foo\n"
        "55005,ZZ,county,North County,,2020-05-01,ab\n"
        "55005,ZZ,county,North County,,2020-05-02,cd\n"
        "55005,ZZ,county,North County,3,2020-05-03,ef\n"
        "55006,ZZ,county,South County,44,2020-05-04,gh\n"
        "55007,ZZ,county,West County,28,2020-05-03,\n"
        "55,ZZ,state,Grand State,,2020-05-01,ij\n"
        "55,ZZ,state,Grand State,42,2020-05-02,\n"
        "55,ZZ,state,Grand State,,2020-05-03,kl\n"
    )
    assert to_dict(["fips", "date"], result) == to_dict(["fips", "date"], expected)


def test_fill_fields_with_data_source():
    existing_df = read_csv_and_index_fips(
        "fips,state,aggregate_level,county,current_icu,preserved\n"
        "55005,ZZ,county,North County,43,ab\n"
        "55006,ZZ,county,South County,,cd\n"
        "55,ZZ,state,Grand State,46,ef\n"
    )
    new_df = read_csv_and_index_fips(
        "fips,state,aggregate_level,county,current_icu\n"
        "55006,ZZ,county,South County,27\n"
        "55007,ZZ,county,West County,28\n"
        "55,ZZ,state,Grand State,64\n"
    )

    datasets = {"existing": existing_df, "new": new_df}

    result, _ = _build_data_and_provenance(
        {"current_icu": ["existing", "new"], "preserved": ["existing"]}, datasets, Override.BY_ROW
    )

    expected = read_csv_and_index_fips(
        "fips,state,aggregate_level,county,current_icu,preserved\n"
        "55005,ZZ,county,North County,43,ab\n"
        "55006,ZZ,county,South County,27,cd\n"
        "55007,ZZ,county,West County,28,\n"
        "55,ZZ,state,Grand State,64,ef\n"
    )

    assert to_dict(["fips"], result) == to_dict(["fips"], expected)


def test_fill_fields_with_data_source_nan_overwrite():
    existing_df = read_csv_and_index_fips(
        "fips,state,aggregate_level,county,current_icu,preserved\n"
        "55,ZZ,state,Grand State,46,ef\n"
    )
    new_df = read_csv_and_index_fips(
        "fips,state,aggregate_level,county,current_icu\n" "55,ZZ,state,Grand State,\n"
    )

    datasets = {"existing": existing_df, "new": new_df}

    result, _ = _build_data_and_provenance(
        {"current_icu": ["existing", "new"], "preserved": ["existing"]}, datasets, Override.BY_ROW
    )

    expected = read_csv_and_index_fips(
        "fips,state,aggregate_level,county,current_icu,preserved\n" "55,ZZ,state,Grand State,,ef\n"
    )

    assert to_dict(["fips"], result) == to_dict(["fips"], expected)


def test_fill_fields_with_data_source_timeseries():
    # Timeseries in existing_df and new_df are merged together.
    existing_df = read_csv_and_index_fips_date(
        "fips,state,aggregate_level,county,cnt,date,foo\n"
        "55005,ZZ,county,North County,1,2020-05-01,ab\n"
        "55005,ZZ,county,North County,2,2020-05-02,cd\n"
        "55005,ZZ,county,North County,,2020-05-03,ef\n"
        "55006,ZZ,county,South County,4,2020-05-04,gh\n"
        "55,ZZ,state,Grand State,41,2020-05-01,ij\n"
        "55,ZZ,state,Grand State,43,2020-05-03,kl\n"
    )
    new_df = read_csv_and_index_fips_date(
        "fips,state,aggregate_level,county,cnt,date\n"
        "55006,ZZ,county,South County,44,2020-05-04\n"
        "55007,ZZ,county,West County,28,2020-05-03\n"
        "55005,ZZ,county,North County,3,2020-05-03\n"
        "55,ZZ,state,Grand State,42,2020-05-02\n"
    )

    datasets = {"existing": existing_df, "new": new_df}

    result, _ = _build_data_and_provenance(
        {"cnt": ["existing", "new"], "foo": ["existing"]}, datasets, Override.BY_ROW
    )

    expected = read_csv_and_index_fips_date(
        "fips,state,aggregate_level,county,cnt,date,foo\n"
        "55005,ZZ,county,North County,1,2020-05-01,ab\n"
        "55005,ZZ,county,North County,2,2020-05-02,cd\n"
        "55005,ZZ,county,North County,3,2020-05-03,ef\n"
        "55006,ZZ,county,South County,44,2020-05-04,gh\n"
        "55007,ZZ,county,West County,28,2020-05-03,\n"
        "55,ZZ,state,Grand State,41,2020-05-01,ij\n"
        "55,ZZ,state,Grand State,42,2020-05-02,\n"
        "55,ZZ,state,Grand State,43,2020-05-03,kl\n"
    )

    assert to_dict(["fips", "date"], result) == to_dict(["fips", "date"], expected)


def test_fill_fields_with_data_source_add_column():
    # existing_df does not have a current_icu column. Check that it doesn't cause a crash.
    existing_df = read_csv_and_index_fips(
        "fips,state,aggregate_level,county,preserved\n"
        "55005,ZZ,county,North County,ab\n"
        "55,ZZ,state,Grand State,cd\n",
    )
    new_df = read_csv_and_index_fips(
        "fips,state,aggregate_level,county,current_icu\n"
        "55007,ZZ,county,West County,28\n"
        "55,ZZ,state,Grand State,64\n",
    )

    datasets = {"existing": existing_df, "new": new_df}

    result, _ = _build_data_and_provenance(
        {"current_icu": ["new"], "preserved": ["existing"]}, datasets, Override.BY_ROW
    )

    expected = read_csv_and_index_fips(
        "fips,state,aggregate_level,county,current_icu,preserved\n"
        "55005,ZZ,county,North County,,ab\n"
        "55007,ZZ,county,West County,28,\n"
        "55,ZZ,state,Grand State,64,cd\n",
    )
    assert to_dict(["fips"], result) == to_dict(["fips"], expected)


def test_fill_fields_with_data_source_no_rows_input():
    existing_df = read_csv_and_index_fips("fips,state,aggregate_level,county,preserved\n")
    new_df = read_csv_and_index_fips(
        "fips,state,aggregate_level,county,current_icu\n"
        "55007,ZZ,county,West County,28\n"
        "55,ZZ,state,Grand State,64\n",
    )

    datasets = {"existing": existing_df, "new": new_df}

    result, _ = _build_data_and_provenance(
        {"current_icu": ["new"], "preserved": ["existing"]}, datasets, Override.BY_ROW
    )

    expected = read_csv_and_index_fips(
        "fips,state,aggregate_level,county,current_icu,preserved\n"
        "55007,ZZ,county,West County,28,\n"
        "55,ZZ,state,Grand State,64,\n"
    )
    assert to_dict(["fips"], result) == to_dict(["fips"], expected)


def column_as_set(
    df: pd.DataFrame,
    column: str,
    aggregation_level,
    state=None,
    states=None,
    on=None,
    after=None,
    before=None,
):
    """Return values in selected rows and column of df.

    Exists to call `make_binary_array` without listing all the parameters.
    """
    rows_binary_array = dataset_utils.make_binary_array(
        df,
        aggregation_level,
        country=None,
        fips=None,
        state=state,
        states=states,
        on=on,
        after=after,
        before=before,
    )
    return set(df.loc[rows_binary_array][column])


def test_make_binary_array():
    df = pd.read_csv(
        StringIO(
            "city,county,state,fips,country,aggregate_level,date,metric\n"
            "Smithville,,ZZ,97123,USA,city,2020-03-23,smithville-march23\n"
            "New York City,,ZZ,97324,USA,city,2020-03-22,march22-nyc\n"
            "New York City,,ZZ,97324,USA,city,2020-03-24,march24-nyc\n"
            ",North County,ZZ,97001,USA,county,2020-03-23,county-metric\n"
            ",,ZZ,97001,USA,state,2020-03-23,mystate\n"
            ",,,,UK,country,2020-03-23,foo\n"
        )
    )

    assert column_as_set(df, "country", AggregationLevel.COUNTRY) == {"UK"}
    assert column_as_set(df, "metric", AggregationLevel.STATE) == {"mystate"}
    assert column_as_set(df, "metric", None, before="2020-03-23") == {"march22-nyc"}
    assert column_as_set(df, "metric", None, after="2020-03-23") == {"march24-nyc"}
    assert column_as_set(df, "metric", None, on="2020-03-24") == {"march24-nyc"}
    assert column_as_set(
        df, "metric", None, state="ZZ", after="2020-03-22", before="2020-03-24"
    ) == {"smithville-march23", "county-metric", "mystate",}
    assert column_as_set(
        df, "metric", None, states=["ZZ"], after="2020-03-22", before="2020-03-24"
    ) == {"smithville-march23", "county-metric", "mystate",}
