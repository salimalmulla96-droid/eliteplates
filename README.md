# Xplate Local Plate Checker

This is a starter local tool for checking UAE plate numbers on Xplate across all cities.

## What it does

You type a plate number, for example:

```text
2007
```

Then the tool checks Xplate city by city and shows results in a table.

It saves results as:

```text
results/xplate_results_2007.csv
results/xplate_results_2007.xlsx
```

## Setup on Windows

Open Command Prompt inside this folder, then run:

```bat
setup.bat
```

This will install the needed Python packages and Playwright browser.

## Run the web app

After setup, run:

```bat
run_app.bat
```

Then open the link Streamlit shows, usually:

```text
http://localhost:8501
```

## Run from terminal only

```bat
python xplate_agent.py 2007
```

## Important safety note

This tool is for personal checking and learning. Do not spam the website. Keep searches slow and reasonable.
