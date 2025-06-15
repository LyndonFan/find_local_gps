import argparse
import polars as pl

from pathlib import Path

DAYS_OF_THE_WEEK = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def flatten_and_add_details(
    surgeries_df: pl.DataFrame, details_df: pl.DataFrame
) -> pl.DataFrame:
    merged = surgeries_df.join(details_df, on="id", how="inner")
    assert len(surgeries_df) == len(merged)
    unnested_opening_times = merged.with_columns(
        [
            pl.col("opening_times").struct.field(d).alias("opening_times_" + d)
            for d in DAYS_OF_THE_WEEK
        ]
    )
    for c in ["name", "address"]:
        assert (unnested_opening_times[c] == unnested_opening_times[c+"_right"]).all()
    unnested_opening_times = unnested_opening_times.drop(["opening_times", "address_right", "name_right"])
    return unnested_opening_times


def add_review_metrics(
    surgeries_df: pl.DataFrame, reviews_df: pl.DataFrame
) -> pl.DataFrame:
    review_aggregates = reviews_df.group_by("id").agg(
        [
            pl.len().alias("num_reviews"),
            pl.col("rating").mean().alias("avg_rating"),
            pl.col("rating").min().alias("min_rating"),
            pl.col("rating").max().alias("max_rating"),
        ]
    )

    surgeries_with_reviews = surgeries_df.join(
        review_aggregates, on="id", how="left"
    ).with_columns(
        [
            pl.col("num_reviews").fill_null(0),
            pl.col("avg_rating").fill_null(0),
            pl.col("min_rating").fill_null(0),
            pl.col("max_rating").fill_null(0),
        ]
    )

    return surgeries_with_reviews


def main(raw_folder: str | Path, postcode: str):
    if not isinstance(raw_folder, Path):
        raw_folder = Path(raw_folder)
    surgeries_df = pl.read_csv(raw_folder / f"{postcode}_gp_surgeries.csv")
    surgeries_details_df = pl.read_json(raw_folder / f"{postcode}_surgery_details.json")
    surgeries_reviews_df = pl.read_json(raw_folder / f"{postcode}_surgery_reviews.json")

    merged_df = flatten_and_add_details(surgeries_df, surgeries_details_df)
    merged_df = add_review_metrics(merged_df, surgeries_reviews_df)
    return merged_df


def parse_arguments():
    parser = argparse.ArgumentParser(description="Process GP surgery data.")
    parser.add_argument("postcode", type=str, help="The UK postcode to process")
    parser.add_argument(
        "--folder", type=str, default="raw", help="The folder containing raw data files"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    result = main(args.folder, args.postcode)
    result.write_csv(f"processed/{args.postcode}_surgery_summaries.csv")
