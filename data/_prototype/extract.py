# coding: utf-8

"""Wrapper building functions to extract data from a given corpus."""

import os
import sys
import time

import numpy as np
import resampy

from data.utils import CONSTANTS, interpolate_missing_values
from utils import check_positive_int, check_type_validity, import_from_string


def build_arguments_checker(corpus, default_articulators):
    """Define and return a function checking features extraction arguments."""
    new_folder = CONSTANTS['%s_processed_folder' % corpus]

    def control_arguments(
            audio_forms, n_coeff, articulators_list,
            ema_sampling_rate, audio_frames_size
        ):
        """Control the arguments provided to extract some features.

        Build the necessary subfolders so as to store the processed data.

        Replace `audio_forms` and `articulators_list` with their
        default values when they are passed as None.

        Return the definitive values of the latter two arguments.
        """
        nonlocal default_articulators, new_folder
        # Check positive integer arguments.
        check_positive_int(n_coeff, 'n_coeff')
        check_positive_int(ema_sampling_rate, 'ema_sampling_rate')
        check_positive_int(audio_frames_size, 'audio_frames_size')
        # Check audio_forms argument validity.
        valid_forms = ['lpc', 'lsf', 'mfcc']
        if audio_forms is None:
            audio_forms = valid_forms
        else:
            if isinstance(audio_forms, str):
                audio_forms = [audio_forms]
            elif isinstance(audio_forms, tuple):
                audio_forms = list(audio_forms)
            else:
                check_type_validity(audio_forms, list, 'audio_forms')
            invalid = [name for name in audio_forms if name not in valid_forms]
            if invalid:
                raise ValueError(
                    "Unknown audio representation(s): %s." % invalid
                )
        # Build necessary folders to store the processed data.
        for name in audio_forms + ['ema']:
            dirname = os.path.join(new_folder, name)
            if not os.path.isdir(dirname):
                os.makedirs(dirname)
        # Check articulators_list argument validity.
        if articulators_list is None:
            articulators_list = default_articulators
        else:
            check_type_validity(articulators_list, list, 'articulators_list')
        # Return potentially altered list arguments.
        return audio_forms, articulators_list

    # Return the defined function.
    return control_arguments


def build_extractor(corpus, initial_sampling_rate):
    """Define and return a function to extract features from an utterance.

    corpus                : name of the corpus from which to import features
    initial_sampling_rate : initial sampling rate of the EMA data, in Hz (int)
    """
    # Load the output path and dependency data loading functions.
    new_folder = CONSTANTS['%s_processed_folder' % corpus]
    load_ema, load_phone_labels, load_wav = import_from_string(
        module='data.%s.raw._loaders' % corpus,
        elements=['load_ema', 'load_phone_labels', 'load_wav']
    )

    def extract_data(
            utterance, audio_forms, n_coeff, articulators_list,
            ema_sampling_rate, audio_frames_size
        ):
        """Extract acoustic and articulatory data of a given {0} utterance.

        This function serves as a dependency for `extract_all_utterances`
        and `extract_utterance_data`, avoiding to check again and again
        the same arguments when using the former while ensuring arguments
        are being checked when using the latter.
        """
        nonlocal initial_sampling_rate, new_folder
        nonlocal load_ema, load_phone_labels, load_wav
        # Load phone labels and compute frames index so as to trim silences.
        labels = load_phone_labels(utterance)
        start_frame = int(np.floor(
            (labels[0][0] if labels[0][1] == '#' else 0) * ema_sampling_rate
        ))
        end_frame = int(np.ceil(
            (labels[-2][0] if labels[-1][1] == '#' else labels[-1][0])
            * ema_sampling_rate
        ))
        # Load EMA data and interpolate NaN values using cubic splines.
        ema, _ = load_ema(utterance, articulators_list)
        ema = np.concatenate([
            interpolate_missing_values(data_column).reshape(-1, 1)
            for data_column in np.transpose(ema)
        ], axis=1)
        # Optionally resample the EMA data.
        if ema_sampling_rate != initial_sampling_rate:
            ema = resampy.resample(
                ema, sr_orig=initial_sampling_rate, sr_new=ema_sampling_rate,
                axis=0
            )
        # Trim edge silences from EMA data and save it.
        ema = ema[start_frame:end_frame]
        np.save(os.path.join(new_folder, 'ema', utterance + '_ema.npy'), ema)
        # Load the audio waveform data, structuring it into frames.
        wav = load_wav(
            utterance, audio_frames_size, hop_time=1000 / ema_sampling_rate
        )
        # Compute each audio features set, trim its edge silences and save it.
        for name in audio_forms:
            audio = (
                getattr(wav, 'get_' + name)(n_coeff, static_only=False)
            )
            audio = audio[start_frame:end_frame]
            path = os.path.join(new_folder, name, utterance + '_%s.npy' % name)
            np.save(path, audio)
    # Adjust the functions's docstring and return it.
    extract_data.__doc__ = extract_data.__doc__.format(corpus)
    return extract_data


def build_features_extraction_functions(
        corpus, initial_sampling_rate, default_articulators, docstring_details
    ):
    """Define and return raw features extraction functions for a corpus.

    corpus                : name of the corpus whose features to extract (str)
    initial_sampling_rate : initial sampling rate of the EMA data, in Hz (int)
    default_articulators  : default articulators to keep (list of str)
    docstring_details     : docstring complement for the returned functions
    """
    # Long but explicit function name; pylint: disable=invalid-name
    # Define auxiliary functions through wrappers.
    control_arguments = build_arguments_checker(corpus, default_articulators)
    extract_data = build_extractor(corpus, initial_sampling_rate)
    # Import the get_utterances_list dependency function.
    get_utterances_list = import_from_string(
        'data.%s.raw._loaders' % corpus, 'get_utterances_list'
    )
    # Define a function extracting features from all utterances.
    def extract_utterances_data(
            audio_forms=None, n_coeff=12, articulators_list=None,
            ema_sampling_rate=200, audio_frames_size=200
        ):
        """Extract acoustic and articulatory data of each {0} utterance.

        audio_forms       : optional list of representations of the audio data
                            to produce, among {{'lsf', 'lpc', 'mfcc'}}
                            (list of str, default None implying all of them)
        n_coeff           : number of static coefficients to compute for each
                            representation of the audio data (int, default 12)
                            Note : dynamic features as well as static and
                            dynamic energy will be included as well with
                            each of the audio forms.
        articulators_list : optional list of raw EMA data columns to keep
                            (default None, implying twelve, detailed below)
        ema_sampling_rate : sample rate of the EMA data to use, in Hz
                            (int, default 200)
        audio_frames_size : number of acoustic samples to include per frame
                            (int, default 200)

        Data extractation includes the following:
          - optional resampling of the EMA data
          - framing of audio data to align acoustic and articulatory records
          - production of various acoustic features based on the audio data
          - trimming of silences at the beginning and end of each utterance

        The produced data is stored to the '{0}_processed_folder' set in the
        json configuration file, where a subfolder is built for each kind of
        features (ema, mfcc, etc.). Each utterance is stored as a '.npy' file.
        The file names include the utterance's name, extended with an indicator
        of the kind of features it contains.

        {1}
        """
        nonlocal control_arguments, extract_data, get_utterances_list
        # Check arguments, assign default values and build output folders.
        audio_forms, articulators_list = control_arguments(
            audio_forms, n_coeff, articulators_list,
            ema_sampling_rate, audio_frames_size
        )
        # Iterate over all corpus utterances.
        for utterance in get_utterances_list():
            extract_data(
                utterance, audio_forms, n_coeff, articulators_list,
                ema_sampling_rate, audio_frames_size
            )
            end_time = time.asctime().split(' ')[-2]
            print('%s : Done with utterance %s.' % (end_time, utterance))
            sys.stdout.write('\033[F')
        # Record the list of articulators.
        path = os.path.join(
            CONSTANTS['%s_processed_folder' % corpus], 'ema', 'articulators'
        )
        with open(path, 'w', encoding='utf-8') as file:
            file.write('\n'.join(articulators_list))

    # Adjust the function's docstring and return it.
    extract_utterances_data.__doc__ = (
        extract_utterances_data.__doc__.format(corpus, docstring_details)
    )
    return extract_utterances_data
