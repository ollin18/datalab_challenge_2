"""
TODO:
 - dfs['Trigger Other'].t_q4: str -> int (?)
"""

import argparse
import json
from multiprocessing import Pool
from pathlib import Path

import pandas as pd
import pkg_resources
from symspellpy import SymSpell

# Global spell checker configuration
sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
dictionary_path = pkg_resources.resource_filename(
    "symspellpy",
    "frequency_dictionary_en_82_765.txt",
)
bigram_path = pkg_resources.resource_filename(
    "symspellpy",
    "frequency_bigramdictionary_en_243_342.txt",
)
# term_index is the column of the term and count_index is the column of the term frequency
sym_spell.load_dictionary(dictionary_path, term_index=0, count_index=1)
sym_spell.load_bigram_dictionary(bigram_path, term_index=0, count_index=2)


def get_parser():
    def parse_bool(x):
        return x.lower() in {'true', 't', '1'}

    parser = argparse.ArgumentParser(
        description="Functions and tools to clean and load the SMAC data for Data Lab challenge 2.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        '--clean_data',
        type=parse_bool,
        default=True,
        help='Applies automated cleaning procedures to the SMAC data.',
    )
    parser.add_argument(
        '--data_kind',
        type=lambda x: x.lower(),
        default='clean',
        choices=['clean', 'raw'],
        help='Determines the data flavor that is loaded. '
             'clean has been manually curated and raw is unchanged.',
    )
    parser.add_argument(
        '--save_csvs',
        type=parse_bool,
        default=False,
        help='Saves data CSVs before automated cleaning has been applied.',
    )
    parser.add_argument(
        '--save_clean_csvs',
        type=parse_bool,
        default=False,
        help='Saves data CSVs after automated cleaning has been applied.',
    )
    parser.add_argument(
        '-v',
        '--verbose',
        action='count',
        default=0,
        help='Determines the level of terminal output.'
    )

    return parser


def main(
        clean_data=True,
        data_kind='clean',
        save_csvs=False,
        save_clean_csvs=False,
        verbose=False,
):
    dfs = load_smac_data(data_kind=data_kind)

    if save_csvs:
        for sheet, df in sorted(dfs.items()):
            df.to_csv(f'../data/{data_kind}/all_paper_data_{sheet.strip().replace(" ", "_")}.csv', index=False)

    if clean_data:
        dfs = clean_smac_data(dfs)

    if save_clean_csvs:
        for sheet, df in sorted(dfs.items()):
            df.to_csv(f'../data/{data_kind}/all_paper_data_{sheet.strip().replace(" ", "_")}_clean.csv', index=False)

    if verbose:
        for label, df in sorted(dfs.items()):
            print(f'{label}:\n{df.dtypes}\n\n')

    # pprint(sorted(dfs['Follow Up Other'].Date_of_Visit.dropna().unique()))


def load_smac_data(data_kind='clean'):
    return {
        path.stem.replace('all_paper_data_', ''): pd.read_csv(path)
        for path in sorted(Path(f'../data/{data_kind}').glob('*.csv'))
    }


def load_smac_data_old(path='../data/clean/all_paper_data.xlsx'):
    dfs = pd.read_excel(
        path,
        sheet_name=[
            'Trigger_NA',
            'Trigger_Ave',
            'Trigger Other',
            'Follow Up',
            'Follow Up Other',
        ],
    )

    dfs['Codebook'] = pd.read_excel(
        path,
        sheet_name='Codebook',
        skiprows=[0],
    )
    return dfs


def clean_smac_data(dfs):
    clean_int_col_map = {'o': 0, 'O': 0, 'nan': 0}
    for i in range(100):
        clean_int_col_map[i] = i

    dfs['Follow_Up'].Children = dfs['Follow_Up'].Children.map(clean_int_col_map)
    dfs['Follow_Up'].r_mc = dfs['Follow_Up'].r_mc.map(clean_int_col_map)
    dfs['Follow_Up'].r_fa = dfs['Follow_Up'].r_fa.map(clean_int_col_map)

    # Fill in the Children column when it is NA and Male_child + Female_child are not NA
    index = (
            dfs['Trigger_Ave'].Children.isna() &
            ~dfs['Trigger_Ave'].Male_child.isna() &
            ~dfs['Trigger_Ave'].Female_child.isna()
    )
    dfs['Trigger_Ave'].Children.loc[index] = (
            dfs['Trigger_Ave'].Male_child.loc[index] +
            dfs['Trigger_Ave'].Female_child.loc[index]
    )

    # Map the time since last ebola case question from a string to an approximate Timedelta
    t_q1_map = {
        'last week': pd.Timedelta(days=7),
        '2-3 weeks': pd.Timedelta(days=17, hours=6),
        '3weeks': pd.Timedelta(days=21),
        '4 weeks or more': pd.Timedelta(days=28),
        '4 weeks 0r m0re': pd.Timedelta(days=28),
        '5 weeks or more': pd.Timedelta(days=35),
    }
    dfs['Trigger_Other'].t_q1 = dfs['Trigger_Other'].t_q1.str.strip().str.lower().map(t_q1_map)

    # Clean up the text based columns
    sheets = ['Trigger_Other', 'Follow_Up_Other']
    str_colz = [
        ['t_q4', 't_q6', 't_q7', 't_q8', 't_q9', 't_q10', 't_q11'],
        ['f_q2', 'f_q3', 'f_q4', 'f_q5', 'f_q6'],
    ]

    for sheet, str_cols in zip(sheets, str_colz):
        for str_col in str_cols:
            map_file = f'../data/column_maps/{sheet}_{str_col}_map.json'
            if not Path(map_file).is_file():
                make_spelling_correction_map(dfs, sheet=sheet, col=str_col)

            with open(map_file) as f:
                str_col_map = json.load(f)
            dfs[sheet][str_col] = (
                dfs[sheet][str_col]
                    .str.lower()
                    .str.strip(' .,\"')
                    .str.replace('  ', ' ')
                    .map(str_col_map)
            )

    # Map the t_q5 column from a string response to a categorical variable
    t_q5_map = {
        'very low': 0,
        'low': 1,
        'medium': 2,
        'high': 3,
        'very high': 4,
        'very hig': 4,
    }
    dfs['Trigger_Other'].t_q5 = dfs['Trigger_Other'].t_q5.str.strip().str.lower().map(t_q5_map)

    return dfs


def make_spelling_correction_map(dfs, sheet, col):
    positions = sorted(
        dfs[sheet][col].str.lower().str.strip(' .,\"').str.replace('  ', ' ').dropna().unique()
    )
    with Pool() as pool:
        fixed_positions = pool.map(fix_spelling_errors, positions)

    with open(f'../data/column_maps/{sheet}_{col}_map.json', 'w') as f:
        json.dump({
            x: y
            for x, y in zip(positions, fixed_positions)
        },
            f,
            indent=4,
            sort_keys=True,
        )


def fix_spelling_errors(sample, threshold=1):
    suggestions = sym_spell.lookup_compound(sample, max_edit_distance=2)

    # Suggestion object attributes:
    #  - term: the corrected string
    #  - distance: the edit distance
    #  - count: Naive Bayes probability of the individual suggestion parts
    suggestion = suggestions[0]
    if suggestion.count > threshold:
        return suggestion.term
    else:
        return sample


if __name__ == '__main__':
    main(**vars(get_parser().parse_args()))
