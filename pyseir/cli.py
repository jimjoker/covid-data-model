import sys, os
import click
import us
import logging
from functools import partial
from pyseir import divide_up_pool, Pool
from pyseir.load_data import cache_all_data
from pyseir.inference.initial_conditions_fitter import generate_start_times_for_state
from pyseir.ensembles.ensemble_runner import run_state
from pyseir.reports.state_report import StateReport
from pyseir.inference import model_fitter
from pyseir.deployment.webui_data_adaptor_v1 import WebUIDataAdaptorV1
from libs.datasets import NYTimesDataset, CDSDataset

sys.path.insert(0, os.path.join(os.path.abspath(os.path.dirname(__file__)), ".."))

root = logging.getLogger()
root.setLevel(logging.INFO)

# handler = logging.StreamHandler(sys.stdout)
handler = logging.FileHandler('myapp.log')
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    "%(asctime)s - %(filename)s - %(lineno)d - %(levelname)s - %(message)s"
)
handler.setFormatter(formatter)
root.addHandler(handler)

nyt_dataset = None
cds_dataset = None


def _cache_global_datasets():
    global nyt_dataset, cds_dataset
    if cds_dataset is None:
        cds_dataset = CDSDataset.local()
    if nyt_dataset is None:
        nyt_dataset = NYTimesDataset.load()


@click.group()
def entry_point():
    """Basic entrypoint for cortex subcommands"""
    pass


@entry_point.command()
def download_data():
    cache_all_data()


def _impute_start_dates(state=None, states_only=False):
    if states_only:
        raise NotImplementedError(
            "Impute start dates does not yet implement support for states_only."
        )

    if state:
        generate_start_times_for_state(state=state)
    else:
        for state_obj in us.STATES:
            _impute_start_dates(state_obj.name)


def _run_mle_fits(state=None, states_only=False):
    _cache_global_datasets()
    if state:
        model_fitter.run_state(state, states_only=states_only)
    else:
        for state_obj in us.STATES:
            _run_mle_fits(state=state_obj.name, states_only=states_only)


def _run_ensembles(state=None, ensemble_kwargs=dict(), states_only=False):
    if state:
        run_state(state, ensemble_kwargs=ensemble_kwargs, states_only=states_only)
    else:
        for state_obj in us.STATES:
            run_state(
                state_obj.name, ensemble_kwargs=ensemble_kwargs, states_only=states_only
            )


def _generate_state_reports(state=None):
    if state:
        report = StateReport(state)
        report.generate_report()
    else:
        for state_obj in us.STATES:
            _generate_state_reports(state_obj.name)


def _map_outputs(
    state=None,
    output_interval_days=4,
    states_only=False,
    output_dir=None,
    run_mode="default",
):
    output_interval_days = int(output_interval_days)
    _cache_global_datasets()
    if state:
        web_ui_mapper = WebUIDataAdaptorV1(
            state,
            output_interval_days=output_interval_days,
            run_mode=run_mode,
            jhu_dataset=nyt_dataset,
            cds_dataset=cds_dataset,
            output_dir=output_dir,
        )
        web_ui_mapper.generate_state(states_only=states_only)
    else:
        for state_obj in us.STATES:
            _map_outputs(
                state_obj.name,
                output_interval_days,
                states_only=states_only,
                run_mode=run_mode,
                output_dir=output_dir,
            )

def _run_all(
    state=None,
    run_mode="default",
    generate_reports=True,
    output_interval_days=4,
    skip_download=False,
    states_only=False,
    output_dir=None,
):
    #_cache_global_datasets()


    #if not skip_download:
    #    cache_all_data()

    root.info(f'the state is [{state}]')
    root.info(f'the states_only is [{states_only}]')
    if state:
        # Deprecate temporarily since not needed.
        if not states_only:
            _impute_start_dates(state)
        _run_mle_fits(state, states_only=states_only)
        # _run_ensembles(
        #     state,
        #     ensemble_kwargs=dict(
        #         run_mode=run_mode,
        #         generate_report=generate_reports,
        #         covid_timeseries=nyt_dataset
        #     ),
        #     states_only=states_only
        # )
        # if generate_reports:
        #     _generate_state_reports(state)
        # _map_outputs(state, output_interval_days, states_only=states_only,
        #              output_dir=output_dir, run_mode=run_mode)
    else:
        if states_only:
            f = partial(
                _run_all,
                run_mode=run_mode,
                generate_reports=generate_reports,
                output_interval_days=output_interval_days,
                skip_download=True,
                states_only=states_only,
                output_dir=output_dir,
            )
            states_at_a_time = divide_up_pool()[1]
            pool = Pool(states_at_a_time)
            pool.starmap(f, [state_obj.name for state_obj in us.STATES])
            pool.close()
            pool.join()

        else:
            root.info(f'breakitup ')
            state_args = []
            for state_obj in us.STATES:
                args = (
                    state_obj.name,  #'state':
                    run_mode,  #'run_mode':
                    generate_reports,  #'generate_reports':
                    output_interval_days,  #'output_interval_days':
                    True,  #'skip_download':
                    states_only,  #'states_only':
                    output_dir,
                )  #'output_dir':
                root.info(f'args {args}')
                state_args.append(args)

            states_at_a_time = divide_up_pool()[1]
            root.info(states_at_a_time)
            pool = Pool(states_at_a_time)
            pool.starmap(_run_all, state_args)
            pool.close()
            pool.join()


@entry_point.command()
@click.option(
    "--state",
    default="",
    help="State to generate files for. If no state is given, all states are computed.",
)
@click.option(
    "--states-only", default=False, is_flag=True, type=bool, help="Only model states"
)
def impute_start_dates(state, states_only):
    _impute_start_dates(state, states_only)


@entry_point.command()
@click.option(
    "--state",
    default="",
    help="State to generate files for. If no state is given, all states are computed.",
)
@click.option(
    "--states-only", default=False, is_flag=True, type=bool, help="Only model states"
)
def run_mle_fits(state, states_only):
    _run_mle_fits(state, states_only=states_only)


@entry_point.command()
@click.option(
    "--state",
    default="",
    help="State to generate files for. If no state is given, all states are computed.",
)
@click.option(
    "--generate-reports",
    default=False,
    is_flag=True,
    type=bool,
    help="If False, skip pdf report generation.",
)
@click.option(
    "--run-mode",
    default="default",
    help="State to generate files for. If no state is given, all states are computed.",
)
@click.option(
    "--states-only", default=False, is_flag=True, type=bool, help="Only model states"
)
def run_ensembles(state, run_mode, generate_reports, states_only):
    _run_ensembles(
        state,
        ensemble_kwargs=dict(run_mode=run_mode, generate_report=generate_reports),
        states_only=states_only,
    )


@entry_point.command()
@click.option(
    "--state",
    default="",
    help="State to generate files for. If no state is given, all states are computed.",
)
def generate_state_report(state):
    _generate_state_reports(state)


@entry_point.command()
@click.option(
    "--state",
    default="",
    help="State to generate files for. If no state is given, all states are computed.",
)
@click.option(
    "--output-interval-days",
    default=4,
    type=int,
    help="Number of days between outputs for the WebUI payload.",
)
@click.option(
    "--run-mode",
    default="default",
    type=str,
    help="State to generate files for. If no state is given, all states are computed.",
)
@click.option(
    "--states-only", default=False, is_flag=True, type=bool, help="Only model states"
)
def map_outputs(state, output_interval_days, run_mode, states_only):
    _map_outputs(
        state,
        output_interval_days=int(output_interval_days),
        run_mode=run_mode,
        states_only=states_only,
    )


@entry_point.command()
@click.option(
    "--state",
    default=None,
    help="State to generate files for. If no state is given, all states are computed.",
)
@click.option(
    "--run-mode",
    default="default",
    type=str,
    help="State to generate files for. If no state is given, all states are computed.",
)
@click.option(
    "--generate-reports",
    default=False,
    type=bool,
    is_flag=True,
    help="If False, skip pdf report generation.",
)
@click.option(
    "--output-interval-days",
    default=4,
    type=int,
    help="Number of days between outputs for the WebUI payload.",
)
@click.option(
    "--skip-download",
    default=False,
    is_flag=True,
    type=bool,
    help="Skip the download phase.",
)
@click.option(
    "--output-dir", default=None, type=str, help="Directory to deploy webui output."
)
@click.option(
    "--states-only", default=False, is_flag=True, type=bool, help="Only model states"
)
def run_all(
    state,
    run_mode,
    generate_reports,
    output_interval_days,
    skip_download,
    output_dir,
    states_only,
):
    _run_all(
        state,
        run_mode,
        generate_reports,
        output_interval_days,
        skip_download=skip_download,
        output_dir=output_dir,
        states_only=states_only,
    )


if __name__ == "__main__":
    entry_point()