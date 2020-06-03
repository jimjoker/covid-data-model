import math
import numpy as np
import logging
import pandas as pd
from sklearn.linear_model import LinearRegression

log = logging.getLogger(__name__)


class LagMonitor:
    """
    Monitors lag in posterior relative to driving likelihood as Bayesian update is repeatedly
    applied. If lag is severe logs a short warning (or a longer one if debug is enabled).
    """

    # TODO add method to support issuing any warning at the end of processing

    def __init__(self, threshold=0.7, days_threshold=4, debug=False):
        self.threshold = threshold
        self.days_threshold = days_threshold
        self.debug = debug
        self.last_lag = 0
        self._reset_()

    def _reset_(self):
        self.lag_days_running = list()
        self.max_lag = 0
        self.total_lag = 0

    def evaluate_lag_using_argmaxes(self, current_day, prev_post_am, prior_am, like_am, post_am):
        # Test if there is lag by checking whether pull of consistent likelihood in one direction
        # can move the value fast enough (as determined by sigma). Looking at argmax values of
        # previous posterior/current prior, current likelihood and current posterior
        p_po_am = prev_post_am
        c_pr_am = prior_am
        c_li_am = like_am
        c_po_am = post_am
        driving_likelihood = c_li_am - c_pr_am
        lag_after_update = c_li_am - c_po_am

        # Is this day lagging more than threshold applied to drive?
        compare_lag = round(self.threshold * abs(driving_likelihood))
        noLag = (
            current_day < 12  # needs to settle in
            or abs(lag_after_update) < 3  # lag is less than 3*.02 = .06 in Reff
            or abs(lag_after_update)
            < compare_lag  # Able to move 1/3 of drive per day -> 3 days lag
            or self.last_lag * lag_after_update < 0  # Drive switched directions
        )
        if self.debug:
            ind = "ok" if noLag else "LAGGING"
            print(
                "day {d} {ind}... prior = {pr}, likelihood drive {dd} -> update {up} (remaining lag = {lag} vs {cmp}) yielding posterior = {po}".format(
                    d=current_day,
                    pr=p_po_am,
                    dd=driving_likelihood,
                    up=c_po_am - c_pr_am,
                    po=c_po_am,
                    lag=lag_after_update,
                    cmp=compare_lag,
                    ind=ind,
                )
            )
        if noLag:  # End of lagging sequence of days
            if len(self.lag_days_running) >= self.days_threshold:  # Need 3 days running to warn
                length = len(self.lag_days_running)
                log.warn(
                    "Reff lagged likelihood (max = %.2f, mean = %.2f) for %d days (from %d to %d)"
                    % (
                        0.02 * self.max_lag,
                        0.02 * self.total_lag / length,
                        length,
                        current_day - length,
                        current_day,
                    )
                )
            self._reset_()
        if abs(lag_after_update) >= 4:  # Start tracking any new lag
            self.lag_days_running.append(
                [
                    current_day,
                    p_po_am,
                    driving_likelihood,
                    c_po_am - c_pr_am,
                    c_po_am,
                    lag_after_update,
                ]
            )
            self.total_lag += lag_after_update
            if abs(lag_after_update) > abs(self.max_lag):
                self.max_lag = lag_after_update
        self.last_lag = lag_after_update


def extrapolate_smoothed_values(series, using_n, replacing_last_n):
    """
    Assumes the replacing_last_n values of the series should be replaced
    Uses the previous using_n values to fit a straight line
    And then extrapolates that fit to do the replacement
    TODO somehow ensuring continuity at the transition to the fit line
    Returning just the extrapolated part of the sequence
    """
    subseries = series.tail(using_n + replacing_last_n).head(using_n)

    # Need these so can adjust last valid point to be 0.,0.
    last_x = series.index.values[-replacing_last_n - 1]
    last_y = series.values[-replacing_last_n - 1]

    # Scale so last point is at 0.,0.
    X = np.array(list(map(lambda d: float(d - last_x), subseries.index.values))).reshape(
        -1, 1
    )  # expects 2d array for X
    Y = subseries.values - last_y

    linear_regressor = LinearRegression(
        fit_intercept=False
    )  # forcing y intercept to be 0. making line fit last point
    linear_regressor.fit(X, Y)  # perform linear regression
    (m, b) = (linear_regressor.coef_[0], linear_regressor.intercept_)

    ext = series.copy()
    for x in series.tail(replacing_last_n).index.values:
        ext._set_value(x, last_y + m * (x - last_x))
    return ext
