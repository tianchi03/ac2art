# coding: utf-8

"""Set of functions to run ABXpy tasks on mngu0 data."""

from ac2art.corpora.prototype.abx import (
    build_h5features_extractor, build_abxpy_callers
)


# Define functions through wrappers; pylint: disable=invalid-name
extract_h5_features = build_h5features_extractor('mngu0')

abx_from_features, make_abx_task, make_itemfile, load_abx_scores = (
    build_abxpy_callers('mngu0')
)