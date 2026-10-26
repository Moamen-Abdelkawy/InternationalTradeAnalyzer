# International Trade Analyzer - Usage Guide

Welcome to the International Trade Analyzer! This comprehensive guide will walk you through every step needed to set up and use this tool, from installing Python to running your first trade analysis.

**No prior experience with programming or the command line is required.**

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Installing Python](#2-installing-python)
3. [Downloading the Repository](#3-downloading-the-repository)
4. [Setting Up the BACI Database](#4-setting-up-the-baci-database)
5. [Obtaining a COMTRADE API Key](#5-obtaining-a-comtrade-api-key)
6. [Installing Required Packages](#6-installing-required-packages)
7. [Running the Analyzer](#7-running-the-analyzer)
8. [Using the Analyzer](#8-using-the-analyzer)
9. [Understanding the Output](#9-understanding-the-output)
10. [Troubleshooting](#10-troubleshooting)
11. [License Information](#11-license-information)
12. [Contact and Support](#12-contact-and-support)

---

## 1. Prerequisites

Before you begin, make sure you have:

- A computer running **Windows**, **macOS**, or **Linux**
- An internet connection
- For BACI queries only: at least **8 GB of free disk space** for the BACI database, plus about **3 GB** more if you build the optional fast BACI cache ([Step 7.4](#step-74-speed-up-baci-queries-optional))
- A web browser
- **Microsoft Excel** and **Microsoft Word**, or free alternatives such as LibreOffice Calc and Writer, to open the results

---

## 2. Installing Python

Python is a programming language that this tool is built with. You need to install it on your computer.

### Step 2.1: Download Python

1. Open your web browser and go to: **https://www.python.org/downloads/**

2. Click the large yellow button that says **"Download Python 3.x.x"** (the exact version number may vary)

   ![Python Download Page](https://www.python.org/static/img/python-logo.png)

   > **Note**: The analyzer works with **Python 3.11 to 3.14**. If the yellow button offers a newer version (3.15 or later), don't use it: scroll down the same page to **"Looking for a specific release?"** and download the latest **3.14** release instead. Some of the packages the analyzer uses are not yet available for newer versions of Python.

### Step 2.2: Install Python

#### On Windows:

1. Locate the downloaded file (usually in your `Downloads` folder) - it will be named something like `python-3.x.x-amd64.exe`

2. **Double-click** the file to run the installer

3. **IMPORTANT**: On the first screen, check the box that says **"Add Python to PATH"** at the bottom. This is crucial!

4. Click **"Install Now"**

5. Wait for the installation to complete, then click **"Close"**

#### On macOS:

1. Locate the downloaded file (usually in your `Downloads` folder) - it will be named something like `python-3.x.x-macos.pkg`

2. **Double-click** the file to run the installer

3. Follow the on-screen instructions, clicking **"Continue"** and **"Agree"** as needed

4. Click **"Install"** and enter your password when prompted

5. Click **"Close"** when finished

### Step 2.3: Verify Python Installation

Let's make sure Python was installed correctly:

#### On Windows:

1. Press the **Windows key** on your keyboard

2. Type `cmd` and press **Enter** to open the Command Prompt

3. Type the following and press **Enter**:
   ```
   python --version
   ```

4. You should see something like `Python 3.x.x`. If you see this, Python is installed correctly!

#### On macOS:

1. Open **Finder** and go to **Applications** > **Utilities** > **Terminal**

2. Type the following and press **Enter**:
   ```
   python3 --version
   ```

3. You should see something like `Python 3.x.x`. If you see this, Python is installed correctly!

Check the version number: it must be between **3.11 and 3.14**. If it is not, install a 3.14 release as described in Step 2.1.

---

## 3. Downloading the Repository

A "repository" (or "repo") is simply a folder containing all the project files. There are two ways to download it:

### Option A: Download as ZIP (Easiest - No Git Required)

1. Go to: **https://github.com/Moamen-Abdelkawy/InternationalTradeAnalyzer**

2. Click the green **"Code"** button

3. Select **"Download ZIP"**

4. Once downloaded, find the ZIP file in your `Downloads` folder

5. **Extract the ZIP file**:
   - **Windows**: Right-click the ZIP file and select **"Extract All..."**, then click **"Extract"**
   - **macOS**: Double-click the ZIP file to extract it

6. Move the extracted folder to a convenient location (e.g., your `Documents` folder)

### Option B: Using Git (For Those Familiar with Git)

If you have Git installed, open a terminal and run:

```bash
git clone https://github.com/Moamen-Abdelkawy/InternationalTradeAnalyzer.git
```

---

## 4. Setting Up the BACI Database

The BACI database provides harmonized bilateral trade data. It's a large file that needs to be downloaded separately. You need it only for BACI queries: if you use COMTRADE only, skip to [Section 5](#5-obtaining-a-comtrade-api-key).

### Step 4.1: Download BACI Data

1. Go to: **https://www.cepii.fr/DATA_DOWNLOAD/baci/doc/baci_webpage.html**

2. Scroll down to find the download section

3. Select **"HS92"** classification (this is the Harmonized System 1992 version)

4. Click to download the database

   > **Note**: The file size is approximately **2.3 GB**. The download may take some time depending on your internet speed.

### Step 4.2: Extract the Downloaded File

1. Locate the downloaded file (it will be a `.zip` file)

2. **Extract the ZIP file**:
   - **Windows**: Right-click the ZIP file and select **"Extract All..."**
   - **macOS**: Double-click the ZIP file

3. After extraction, you should have a folder named something like `BACI_HS92_V202601`

   This folder should contain files like:
   - `BACI_HS92_Y1995_V202601.csv`
   - `BACI_HS92_Y1996_V202601.csv`
   - ... (one file for each year)
   - `country_codes_V202601.csv`
   - `product_codes_HS92_V202601.csv`

### Step 4.3: Place the BACI Data in the Correct Location

1. Open the International Trade Analyzer folder that you downloaded earlier

2. Navigate to: `data` > `BACI`

3. **Move or copy** the entire `BACI_HS92_V202601` folder into the `BACI` directory

   Your folder structure should now look like this:
   ```
   InternationalTradeAnalyzer/
   └── data/
       └── BACI/
           └── BACI_HS92_V202601/
               ├── BACI_HS92_Y1995_V202601.csv
               ├── BACI_HS92_Y1996_V202601.csv
               ├── ... (more year files)
               ├── country_codes_V202601.csv
               └── product_codes_HS92_V202601.csv
   ```

---

## 5. Obtaining a COMTRADE API Key

COMTRADE is the analyzer's main data source: each country's own reports to the United Nations. To download its data, you need a free API key.

> **Using BACI only?** BACI queries run without a key, but the key is worth getting: with it, every BACI report checks its totals against the reporter's own COMTRADE figures ([Section 9.9](#99-baci-and-comtrade-strengths-limits-and-which-to-use)); without it, the report says the check was not made. BACI queries also need an internet connection, because the analyzer reads COMTRADE's public lists of country names and product descriptions.

### Step 5.1: Register for a COMTRADE Account

1. Go to: **https://uncomtrade.org/docs/api-subscription-keys/**

2. Follow the instructions on that page to:
   - Create a free account
   - Subscribe to the **"comtrade - v1"** API (it's free!)
   - Obtain your API keys

3. After registration, you will receive:
   - A **Username** (usually your email address)
   - A **Primary Key** (a long string of letters and numbers)
   - A **Secondary Key** (another long string)

   **Keep these safe** - you'll need them in the next step!

### Step 5.2: Configure Your API Credentials

Your credentials go in a file named `SUBSCRIPTION_KEY.env` in the International Trade Analyzer folder. The file is not part of the download, so that nobody's key is ever shared: you create it yourself.

1. Open a **text editor**:
   - **Windows**: **Notepad**
   - **macOS**: **TextEdit**, then choose **Format** > **Make Plain Text**

2. Type the following, with your own credentials **between the double quotes**:

   ```
   # comtrade - v1 API Credentials
   COMTRADE_USERNAME="john.smith@email.com"
   PRIMARY_KEY="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
   SECONDARY_KEY="p6o5n4m3l2k1j0i9h8g7f6e5d4c3b2a1"
   ```

   The analyzer uses the `PRIMARY_KEY`; the other two lines are there for your own reference.

3. **Save the file** in the International Trade Analyzer folder, named exactly `SUBSCRIPTION_KEY.env`:
   - **Windows**: in Notepad's **Save as type** list, choose **All files (\*.\*)**, so that Notepad does not add `.txt` to the name
   - **macOS**: if TextEdit offers to add `.txt`, choose **Use ".env"**

The file stays on your computer: the repository is set to ignore it, so it is never uploaded with the code.

---

## 6. Installing Required Packages

The analyzer needs some additional Python packages to work. Let's install them.

### Step 6.1: Open the Terminal/Command Prompt

#### On Windows:

1. Open **File Explorer** and navigate to the International Trade Analyzer folder

2. Click on the **address bar** at the top (where it shows the folder path)

3. Type `cmd` and press **Enter**

   This opens a Command Prompt window already in the correct folder!

   Alternatively:
   - Press **Windows key + R**
   - Type `cmd` and press **Enter**
   - Then navigate to the folder by typing:
     ```
     cd "C:\path\to\InternationalTradeAnalyzer"
     ```
     (Replace with the actual path to your folder)

#### On macOS:

1. Open **Terminal** (Applications > Utilities > Terminal)

2. Type `cd ` (with a space after it)

3. Drag and drop the International Trade Analyzer folder into the Terminal window

4. Press **Enter**

### Step 6.2: Install the Required Packages

With the terminal open in the correct folder, type the following command and press **Enter**:

#### On Windows:
```
pip install -r requirements.txt
```

#### On macOS:
```
pip3 install -r requirements.txt
```

This will download and install all the necessary packages. You'll see text scrolling as packages are installed. Wait until you see the command prompt again - this means it's finished.

> **Updating from an earlier version?** Run the same command again. This version uses new packages: XlsxWriter (the Excel workbook), python-docx (the Word report) and pyarrow (fast BACI reading). The requirements file now lists only the eight packages the analyzer uses; pip installs what they need.

---

## 7. Running the Analyzer

Now you're ready to run the analyzer! There are three ways to run it:

- **Interactive** ([Step 7.1](#step-71-start-the-analyzer-interactive)): the analyzer asks you questions one by one. Best for your first queries.
- **Command line** ([Step 7.2](#step-72-run-one-query-from-the-command-line)): you type the whole query in one line. Handy for repeating a query.
- **Batch** ([Step 7.3](#step-73-run-many-queries-at-once-batch)): you list many queries in a CSV file and run them all at once.

All three give the same results (see [Section 9](#9-understanding-the-output)).

> **On macOS**, type `python3` wherever this guide says `python`.

### Step 7.1: Start the Analyzer (Interactive)

With the terminal still open in the International Trade Analyzer folder, type:

#### On Windows:
```
python trade_analyzer.py
```

#### On macOS:
```
python3 trade_analyzer.py
```

Press **Enter** and the analyzer will start! [Section 8](#8-using-the-analyzer) explains each question.

### Step 7.2: Run One Query from the Command Line

You can give the whole query at once instead of answering questions. For example, Egypt's wheat imports from 2015 to 2024, from BACI:

```
python trade_analyzer.py --source baci --reporter Egypt --product 1001 --flow M --period 2015-2024
```

Or a report on Egypt's monthly wheat imports from Russia in 2024, from COMTRADE:

```
python trade_analyzer.py --source comtrade --freq M --period 202401-202412 --reporter 818 --product 1001 --flow M --partner "Russian Federation"
```

| Option | What to give | Example |
|--------|--------------|---------|
| `--source` | `baci` or `comtrade` | `--source baci` |
| `--freq` | `A` annual (the default) or `M` monthly (COMTRADE only) | `--freq M` |
| `--period` | A year or a range of years; for monthly data, a month or a range of months | `--period 2015-2024`, `--period 202401-202412` |
| `--reporter` | The reporter country, by name or code | `--reporter Egypt`, `--reporter 818` |
| `--partner` | Optional: one partner country, by name or code, for a report on the trade between the reporter and that partner ([Section 9.8](#98-the-partner-report)). Leave it out to analyze all partners | `--partner "Russian Federation"` |
| `--product` | An HS code with 2, 4 or 6 digits, or `TOTAL`, `AG2`, `AG4`, `AG6` | `--product 1001` |
| `--flow` | `M` imports or `X` exports | `--flow M` |
| `--metric` | The metric used to rank partners and measure growth (default `value`). BACI: `value` or `quantity`. COMTRADE: `value`, `cif`, `fob`, `netweight`, `grossweight` or `quantity` | `--metric quantity` |
| `--out` | The folder for the results (default `output`) | `--out results` |

Tips:
- Put names that contain spaces in double quotes: `--partner "Russian Federation"`.
- A name must match one country only. If it matches several, the analyzer lists them and stops; use the country code instead.
- To see every option, type `python trade_analyzer.py --help`.

### Step 7.3: Run Many Queries at Once (Batch)

The main folder has an example file, **`batch_example.csv`**, that you can run as it is or copy and edit:

```
source,freq,period,reporter,partner,product,flow,metric
baci,A,2015-2024,Egypt,,1001,M,value
baci,A,2015-2024,Egypt,Russian Federation,1001,M,value
comtrade,A,2021-2024,Egypt,,2523,X,netweight
comtrade,A,2021-2024,Egypt,,2515,X,value
comtrade,A,2022-2024,Egypt,,0102,M,quantity
comtrade,M,202401-202412,Egypt,,1001,M,value
comtrade,A,2024,Egypt,,AG2,X,value
```

Its rows show each kind of query: BACI for all partners and for the trade with one partner (Russian Federation); COMTRADE annual data measured by net weight, by value, and by quantity for a product measured in one unit (live bovine animals, counted in items); monthly data; and all products by HS chapter (`AG2`).

1. Create a CSV file with one query per row, or edit a copy of `batch_example.csv`. The columns have the same names as the command-line options:
   - Leave `partner` empty to analyze all partners; name a partner for a report on the trade with it.
   - Leave `freq` empty for annual data, and `metric` empty for value.
   - You can make the file in Excel and save it as **CSV UTF-8**. If Excel drops the leading zero of a product code (`0401` becomes `401`), the analyzer adds it back.

2. Run it:

   ```
   python trade_analyzer.py --batch batch_example.csv
   ```

   (or the name of your own file).

Each query gets its own output folder. A query that fails does not stop the others. At the end, the analyzer lists each query with ✓ (done) or ✗ (failed, with the reason).

### Step 7.4: Speed Up BACI Queries (Optional)

Reading a year of BACI from the CSV files takes a few seconds. You can convert the files once to a compact format (Parquet) that loads in a fraction of a second:

```
python trade_analyzer.py --build-baci-cache
```

- It takes a few minutes (about 5 seconds per year) and about 100 MB of disk space per year, or up to about 3 GB for the whole database.
- The converted files go to `data/BACI/BACI_HS92_V202601/parquet/`. From then on, BACI queries use them automatically, with the same results.
- Keep the original CSV files: the cache is made from them.
- If you add new BACI files later, run the command again. Years that are already converted are skipped.

### Step 7.5: Update the Inflation Table (Optional)

The analyzer also reports growth in constant dollars, using the US consumer price index (CPI) published by the World Bank. The table comes with the analyzer, in `data/meta/us_cpi_worldbank.csv`. When the World Bank publishes a new year, update the table with:

```
python trade_analyzer.py --update-cpi
```

Until the World Bank publishes a year, values for that year in constant dollars are shown as Missing.

---

## 8. Using the Analyzer

The analyzer will guide you through a series of questions. Here's what each step means:

### Step 8.1: Data Frequency

```
============================================================
DATA FREQUENCY
============================================================
Select the frequency of data for analysis.

VALID INPUTS:
  A  or  Annual   :  Yearly data
  M  or  Monthly  :  Monthly data (COMTRADE only)

Enter frequency:
```

- Type `A` for annual (yearly) data, or `M` for monthly data
- **Note**: Monthly data is only available through COMTRADE, not BACI

### Step 8.2: Data Source

```
============================================================
DATA SOURCE
============================================================
Select the data source for analysis.

VALID INPUTS:
  B  or  BACI      :  BACI database (1995-2024, harmonized)
  C  or  COMTRADE  :  UN COMTRADE API (as reported by countries)
```

- **BACI**: Uses the downloaded database (1995-2024), in which CEPII reconciles the two countries' reports of each flow
- **COMTRADE**: Uses the API, with data as reported by countries (1962-present)
- If you chose monthly data in Step 8.1, this question is skipped: monthly data comes from COMTRADE

> **Important — choosing the source.** For one country's own trade, especially totals at the 4-digit level and above, COMTRADE is usually the safer choice. BACI can count the same trade twice when the two countries put it under different 6-digit codes: Egypt's wheat imports in BACI, for example, are 1.3 to 1.9 times Egypt's own reported figures in 2015–2019. BACI is the right choice, and often the only one, for countries or years not reported to COMTRADE, for consistent series from 1995 to 2024, and for many-country comparisons at the 6-digit level. [Section 9.9](#99-baci-and-comtrade-strengths-limits-and-which-to-use) explains when and why.

### Step 8.3: Period Selection

Enter the period you want to analyze.

For annual data:
- Single year: `2023`
- Year range: `2018-2023`
- BACI covers 1995-2024; COMTRADE goes back to 1962

For monthly data:
- Single month: `202312` (December 2023)
- Month range: `202301-202312`

**Tip**: Growth over the whole period (CAGR) needs at least two years, and trend growth at least three. For monthly data, both use complete calendar years only.

### Step 8.4: Reporter Country

Enter the country whose trade you want to analyze:
- By name: `Egypt`, `United States`, `China`
- By code: `818` (Egypt), `842` (USA), `156` (China)

The analyzer shows the country it found; type `Y` to confirm. If several countries match, it lists them with their codes, and you can type the code. If no country matches, it suggests similar names (for example `Colombia` for `Columbia`).

Reference: Country codes can be found in `data/meta/country_codes_V202601.csv`

### Step 8.5: Product Code

Enter the HS product code:
- 2-digit chapter: `10` (Cereals)
- 4-digit heading: `1001` (Wheat)
- 6-digit subheading: `100190` (Wheat, other)

Special codes:
- `TOTAL`: all products together
- `AG2`, `AG4`, `AG6`: all products, broken down by HS chapter, heading or 6-digit subheading

If the code has subcategories, the analyzer lists them, and the analysis covers each one, product by product. Type `Y` to confirm the code.

The list depends on the data source, because the two sources use different editions of the HS classification. For COMTRADE, each subcategory shows in brackets the HS editions it exists in, for example for `0401`:

```
  040110: …of a fat content, by weight, not exceeding 1%  [all HS editions]
  040120: …of a fat content, by weight, exceeding 1% but not exceeding 6%  [all HS editions]
  040130: Of a fat content, by weight, exceeding 6 %  [HS 1992–2007]
  040140: …of a fat content, by weight, exceeding 6% but not exceeding 10%  [HS 2012 onwards]
  040150: …of a fat content, by weight, exceeding 10%  [HS 2012 onwards]
```

BACI lists only the HS 1992 codes (here 040110, 040120 and 040130), because it converts every year to that edition. [Section 9.4](#94-hs-editions) explains what this means for your results.

**Note**: Codes in chapters 01-09 start with a zero, e.g. `0401` (Milk and cream). If you leave the zero out (`401`), it is added back automatically.

Reference: Product codes can be found in `data/meta/product_codes_HS92_V202601.csv`

### Step 8.6: Trade Direction

- `M` or `Imports`: Goods coming INTO the reporter country
- `X` or `Exports`: Goods going OUT of the reporter country

### Step 8.7: Partner Selection

- `A` or `All`: Analyze trade with all partners
- `S` or `Specific`: A report on the trade between the reporter and one partner country. You then enter the partner the same way as the reporter (Step 8.4). The whole report is then about the two countries: see [Section 9.8](#98-the-partner-report).

### Step 8.8: Metric Selection

Choose the metric used to rank trading partners and measure growth.

For BACI, the question comes right away:
- `V` or `Value`: Trade value in million USD
- `Q` or `Quantity`: Quantity in metric tons

For COMTRADE, the question comes after the data has been downloaded. It lists only the metrics in COMTRADE's answer, with the number of records of the products that report each one. The quantity is listed unit by unit, as COMTRADE gives it, including N/A (no quantity reported), for example:

```
  1  or  V   :  Value (million USD) (285 records)
  2  or  NW  :  Net weight (t) (245 records, 30 of them estimated by UN Comtrade)
  3  or  QTY :  Quantity, in the unit COMTRADE gives (218 records)
                N/A (no quantity reported): 67 records, 12 product(s)
                l (Volume in liters): 190 records, 14 product(s)
                u (Number of items): 28 records, 9 product(s)
```

**Quantity** stays in the unit COMTRADE gives (kg, number of items, litres...), because that unit reflects the nature of the product: number of animals for live bovine animals, for example. It suits products measured in one unit. Quantities in different units are never added together: if the products of your query use more than one unit, the analyzer refuses quantity and shows which products share a unit, so that you can analyse each group in a query of its own, or choose value or net weight instead:

```
✗ Quantities here are in 2 different units (kg, u), and quantities in different units are never added together. Products in the same unit can be analysed by quantity together, in a query of their own:
  kg (Weight in kilograms): 870810, 870821, ...; all the products of 8708, 8714, 8715 here are in kg
  u (Number of items): 870121, 870122, ...; all the products of 8701, 8702, 8703, ... here are in u
  N/A (no quantity reported): 870110, 870191, ...
Or choose value or net weight, which can be added across all these products.
```

On the command line or in a batch file, `--metric quantity` is refused the same way, with the same message. N/A is not a different unit: it means COMTRADE has no quantity for that record, which is shown as Missing.

**Note**: Whichever metric you choose, the workbook also has the others: for BACI, value and quantity; for COMTRADE, value and net weight, plus every metric in the Raw data sheet.

**Missing data**: Sources do not report every figure. BACI, for example, leaves the quantity blank for some flows. Such figures are shown as **Missing**, and so is every total, share or growth rate that depends on them. The analyzer never estimates or fills them in. See [Section 9.3](#93-missing-na-mixed-units-and-source-estimates).

**Estimates in the database**: COMTRADE marks some weights and quantities as estimated by UN Comtrade rather than reported by the country. These figures are part of the database, so the analyzer uses them as COMTRADE gives them and marks them clearly in every output.

### Step 8.9: The Results

The analyzer then builds the report. In the terminal, it shows:
- **Key findings**: a few sentences on the trend, the largest partners, growth, concentration, data gaps, the source's own estimates, and the HS editions when the data spans more than one
- A table of the totals by year (or month), with growth and the largest partner's share
- Where the files are

For a partner report, the findings are about the two countries, and the table gives the partner's figure, growth, share and rank in each period.

Finally, it asks `Run another analysis? (Y/N)`.

---

## 9. Understanding the Output

### 9.1 Where the Results Go

Each query gets its own folder in `output`, named after the query:

```
output/
└── Egypt_imp_HS1001_2015-2024_BACI/
    ├── Egypt_imp_HS1001_2015-2024_BACI.xlsx   ← the Excel workbook
    ├── report.docx                             ← the Word report
    ├── summary.md                              ← a one-page summary
    └── charts/                                 ← the charts (PNG images)
```

The folder name reads: reporter, `imp` or `exp`, product, partner (if you chose one), period and source. For example: `Egypt_exp_TOTAL_Kenya_2019-2023_COMTRADE`.

Running the same query again replaces the files in its folder.

When the raw data or the list of data gaps has more than 150,000 rows, it is saved next to the workbook as `raw_data.csv` or `data_gaps.csv` instead, and its sheet says so.

**Units.** Every table, chart, report and summary uses the same units, whichever database the data comes from:

| Measure | Unit in the results | Unit in the databases |
|---------|---------------------|-----------------------|
| Value, CIF value, FOB value | million USD | BACI: thousand USD; COMTRADE: USD |
| Net weight, gross weight | metric tons (t) | COMTRADE: kg |
| Quantity | as the database gives it: BACI metric tons; COMTRADE the product's own unit, such as kg, u (number of items) or l (litres) | the same |
| Unit value | USD per metric ton | — |

The quantity's unit is in every heading, such as **Quantity (u)**, and the About sheet and chart subtitles say what it means (u is number of items). The **Raw data** sheet always keeps each database's own units.

### 9.2 The Excel Workbook

The workbook holds everything: the raw data of the query, the analysis for each year (or month), and the analysis for the whole period. Some sheet names depend on the query: partners are called **Suppliers** for imports and **Markets** for exports, and tables are **by year** or **by month**.

| Sheet | What it shows |
|-------|---------------|
| **About** | The query, the source and the HS edition of its data, how missing data and the source's estimates are recognised, the definition of every measure, data checks, and links to every sheet |
| **Summary** | Key figures, key findings, the totals by period and the overview chart |
| **Yearly** (or **Monthly**) | One row per period: totals, growth on the previous period, unit value, number of partners, the largest partner, concentration and the share of each total the source estimated; below it, growth over the whole period |
| **Annual totals** | Monthly queries only: the totals for each complete calendar year |
| **Suppliers** (or **Markets**) | Every partner over the whole period: rank, totals, share, unit value, first and last period, change, CAGR (also in constant dollars), change in share, periods with trade, peak period and status |
| **Suppliers by year** | The chosen metric by partner and period |
| **Quantity by year** (or the other metrics) | The same for each of the other metrics |
| **Shares by year** | Each partner's share of each period's total |
| **Growth by year** | Each partner's growth on the previous period |
| **Products**, **Products by year** | The same analysis by HS product; when the data spans more than one HS edition, an **HS editions** column and a note (see [Section 9.4](#94-hs-editions)) |
| **Data gaps** | Every data point the source does not report, with the reason (left out when there are none) |
| **Source estimates** | Every figure the database itself marks as an estimate, with its flag; the analysis uses each one as given (left out when there are none) |
| **COMTRADE check** | BACI queries only: BACI's total for each year beside the reporter's own COMTRADE figure for the same code and flow, with the ratio, as a check of BACI ([Section 9.9](#99-baci-and-comtrade-strengths-limits-and-which-to-use)); no figure of the report uses it |
| **Raw data** | Every record of the query, exactly as the source delivers it (for COMTRADE, with its flags and its partner World totals), in an Excel table you can filter and sort |
| **Charts** | Every chart of the report |

A partner report has a workbook of its own: see [Section 9.8](#98-the-partner-report).

### 9.3 Missing, n/a, Mixed Units and Source Estimates

Some cells hold words instead of numbers:

| Cell | Meaning |
|------|---------|
| **Missing** (orange) | The source does not report this figure, or a figure it depends on. For example, a year's total quantity is Missing when any of that year's flows has no quantity |
| **n/a** | The measure is not defined, for example growth from a year without trade, or a CAGR whose first or last year had no trade |
| **Mixed units** | COMTRADE quantities recorded in different units (for example kilograms and items), which are never added. The analyzer refuses quantity for a query whose products use more than one unit (Step 8.8), so this is only a safeguard |

**Where the figures come from.** Every figure comes from the records the source gives for it:
- **COMTRADE**: the totals are COMTRADE's own figures for the code you asked for with partner **World**, the same figures the COMTRADE website shows when you choose partner World. The partner figures are COMTRADE's figures for that code by partner, and the product figures are each HS 6-digit product's own figures. Only where COMTRADE leaves a total empty does the analyzer add up the partners, and the key findings say so.
- **BACI** gives flows between two countries only, one row per HS 6-digit product, so its totals are those flows added up. When two countries put the same trade under different 6-digit codes, BACI keeps both countries' reports and these totals count that trade twice: see [Section 9.9](#99-baci-and-comtrade-strengths-limits-and-which-to-use).

Because COMTRADE reports each level separately, the products do not always add up to the total: a product can lack a quantity that COMTRADE's total for the heading includes. The checks on the About sheet show whether the partners and the products add up to the total.

**Nothing is estimated.** The analyzer never estimates, interpolates or fills in a missing figure, and never calculates a total from part of the data. The Data gaps sheet lists every missing data point with its period, partner, product and reason (and its value in million USD where the source reports one). Whether to take the figure from the other source, add it from elsewhere, or leave it missing is up to you.

What counts as missing:
- **BACI**: a quantity left blank in the BACI file
- **COMTRADE**: a value or weight the API leaves empty; a weight or quantity recorded as 0 on a flow that has a value; a quantity whose unit is N/A; and any period the country has not reported to COMTRADE. A total is Missing only when COMTRADE's own total (partner World) is empty and its partners cannot be added up either

The Raw data sheet always shows exactly what the source returned, for example a weight of 0, even where the analysis shows Missing.

When the chosen metric has gaps, partners are listed by a metric without gaps (usually value) and the Rank column is left blank.

**Estimates in the database.** COMTRADE marks some weights and quantities as estimated by UN Comtrade rather than reported by the country (its `isNetWgtEstimated`, `isGrossWgtEstimated` and `isQtyEstimated` flags). These figures are part of the database, so the analyzer uses them exactly as COMTRADE gives them, and says so:
- Every figure in the workbook's tables that includes one is shown in **blue**
- The Yearly (or Monthly) sheet gives the share of each total that UN Comtrade estimated
- The **Source estimates** sheet lists each estimated figure, with its flag
- The key findings, the Word report, `summary.md` and the chart footnotes say how many figures are estimates

BACI has no such flags.

### 9.4 HS Editions

The Harmonized System is revised every five years or so (HS 1992, 1996, 2002, 2007, 2012, 2017 and 2022), and some codes change: a code can be split into several, merged or removed. For example, HS 2012 replaced `040130` (milk and cream with more than 6% fat) with `040140` (6% to 10%) and `040150` (over 10%).

- **BACI** converts every year to HS 1992, so its codes are the same throughout. In BACI, `040130` covers all milk and cream over 6% fat, in every year.
- **COMTRADE** keeps each country's data in the HS edition it reported in, and countries change editions over time. Egypt, for example, reported 2008–2013 in HS 2007 and 2014–2021 in HS 2012, so its milk imports appear under `040130` up to 2013 and under `040140` and `040150` from 2014.

The analyzer shows the codes as the source reports them; it never converts one edition into another. It states the editions in the outputs instead:
- The About sheet gives the HS edition of the data for each period
- When a COMTRADE query spans more than one edition, the key findings and the Products sheets say so, and the **HS editions** column shows which editions each code exists in. A code that is not in every edition the query uses appears only in some years: in the example above, `040130` would look as if trade stopped in 2014, when in fact the product moved to the new codes
- The product question shows the editions of each subcategory (Step 8.5)

To compare BACI and COMTRADE, compare them at the level of a code that exists in every edition, such as the heading `0401`. At the 6-digit level, BACI's `040130` corresponds to COMTRADE's `040140` plus `040150` in years reported in HS 2012 or later.

### 9.5 Growth and Other Measures

The About sheet defines every measure. In short:

| Measure | Meaning |
|---------|---------|
| **Growth** | Change on the previous year (or month). Monthly data also compares each month with the same month a year earlier |
| **CAGR** | Compound annual growth rate between the first and the last year: (last / first)^(1 / years between) − 1 |
| **Trend growth** | The annual growth of a trend fitted to every year; steadier than CAGR when an end year is unusual. Needs at least three years, all with trade |
| **Constant dollars** | Values adjusted for US inflation (US CPI, from the World Bank), so that growth is in real terms. For annual queries measured in money |
| **Share** | A partner's or product's part of the period's total |
| **Change in share** | The change in share between the first and the last period, in percentage points (pp) |
| **Unit value** | Value divided by quantity (BACI) or net weight (COMTRADE), in USD per metric ton |
| **HHI** | Herfindahl-Hirschman index of concentration across partners: below 1,500 unconcentrated, 1,500 to 2,500 moderately concentrated, above 2,500 highly concentrated |
| **Status** | Continuing (trade in the first and last period), New (none in the first), Lost (none in the last), Intermittent (trade only in between), Unknown (the source has no data for the first or last period) |

For monthly queries, CAGR and trend growth use complete calendar years only.

### 9.6 The Charts

The `charts` folder holds report-ready PNG charts, numbered in reading order. Each title states the main point of its chart, for example "Russian Federation was the largest supplier, with 57% of the total". A chart that does not apply to the query is left out.

| Chart | What it shows |
|-------|---------------|
| `01_overview.png` | The trend by year (or month), with the headline figures |
| `02_partners.png` | The largest partners over the whole period |
| `03_partners_by_period.png` | The largest partners in each period, as a heat map |
| `04_shares.png` | How the partners' shares changed over time |
| `05_growth.png` | The large partners' CAGR and change in share |
| `06_concentration.png` | Concentration (HHI) and the share of the three largest partners |
| `07_products.png` | The largest products |
| `09_seasonality.png` | Monthly queries only: each month across the years |

A figure the source does not report is never drawn as zero: the charts label it Missing (or hatch it, in the heat map). When a chart shows figures that include the source's own estimates, its footnote says so. The same charts are in the workbook's Charts sheet. A partner report has charts of its own (Section 9.8).

### 9.7 The Word Report and the Summary

- **`report.docx`** is a report you can edit and share: the key findings and figures, the scope and method, a numbered section for each chart with its table, and finally the data gaps, source estimates and checks. The pages are numbered, and each main section starts on a new page; the small chart sections (shares, growth, concentration, products and seasonality) follow on the same page.
- **`summary.md`** is a one-page summary in Markdown: key findings, key figures, the totals by period, the top partners and the list of files. It opens in any text editor and displays nicely on GitHub.

### 9.8 The Partner Report

When you choose a partner, the report is about the trade between the two countries. The reporter's trade with every partner is still read, because the partner's share, rank and competitors need it, but the workbook, the charts, the Word report and the summary are about the partner. The report answers these questions:

| Question | What the report shows |
|----------|-----------------------|
| How much do the two countries trade, and how is it changing? | The trade with the partner by period: value, weight or quantity, growth, CAGR, trend growth, constant dollars and unit value |
| How much does the reporter rely on the partner? | The partner's share of the reporter's total and its rank by period, its growth against the total's, and its part of the total's change between the first and the last year |
| Who competes with the partner? | The reporter's largest partners over the whole period, with the partner shaded, and their shares by period |
| At what price? | The partner's unit value by period, against all partners together and against its largest competitors |
| Which products? | The products traded with the partner, and the partner's share of the reporter's trade in each |
| How much does the partner rely on the reporter? | The reporter's share of the partner's trade in the other direction (for an imports query, the partner's exports to every country), its rank among the partner's markets or suppliers, and the partner's largest markets or suppliers |
| Do the two countries' figures agree? | COMTRADE only: the reporter's figures beside the partner's own figures for the same trade, with the difference and the ratio |
| What flows the other way? | The reporter's trade with the partner in the other direction, and the balance of trade in value |

**Where the partner's side comes from.**
- **BACI**: the partner's rows in the same BACI files, read in the same pass over each year. BACI combines the exporter's and the importer's reports into one figure per flow and 6-digit product, so there is no second figure to compare; where the two countries used different 6-digit codes, it keeps both reports instead (Section 9.9). The report gives the number of countries BACI records for the partner each year, so you can see when its coverage changes.
- **COMTRADE**: the partner's own reports, which take about twice as many requests as an All-partners query. A period the partner has not reported to COMTRADE has no figures: they are Missing, with that reason, and nothing replaces them. Russia, for example, has not reported to COMTRADE since 2021. When the partner did not report every period, its largest markets or suppliers are shown for the latest period it reported in full.

**The two countries' figures** are shown as each country reports them, without adjustment. They usually differ: imports are usually valued CIF (with freight and insurance) and exports FOB, and the two countries may record a shipment in different periods, under different codes or with a different partner. The analyzer does not correct or explain the difference.

**HS editions.** Each country reports in its own HS edition. When the partner reported a period in an edition that has no such code (for example `100190`, which exists up to HS 2007), that period is Missing for the partner, with the reason, rather than looking as if there was no trade.

The workbook:

| Sheet | What it shows |
|-------|---------------|
| **About**, **Summary** | As in every report, about the two countries |
| **Yearly** (or **Monthly**) | The trade with the partner by period: each metric and its growth, unit value against all partners, constant dollars, share and rank; growth over the whole period below |
| **Annual totals** | Monthly queries only: complete calendar years, for the partner and for all partners |
| **Market position** | The partner's figure against the total by period: share, rank, growth against the total's and the largest partner; below it, the partner's part of the total's change |
| **Competitors** | The reporter's 10 largest partners, and the partner if it is not among them, with the partner's row shaded; their shares by period below |
| **Prices** | Unit values by period: the partner, all partners together and the largest competitors |
| **Products**, **Products by year** | The products traded with the partner, with the partner's share of the reporter's trade in each |
| **Partner side** | The reporter's share and rank in the partner's trade by period, the number of countries recorded, and the partner's largest markets or suppliers |
| **Both reports** | COMTRADE only: the two countries' figures side by side, metric by metric |
| **Other direction** | The trade the other way by period, the balance of trade, and its products |
| **Data gaps**, **Source estimates** | As in every report, for each view of the trade, with a column saying which |
| **COMTRADE check** | BACI only: BACI's totals beside the reporter's own COMTRADE figures, for all partners and for the partner (Section 9.9) |
| **Raw data**, **Raw data, partner side**, **Raw data, other direction** | The records of each view, exactly as the source delivers them |

The charts:

| Chart | What it shows |
|-------|---------------|
| `01_trade_with_partner.png` | The trade with the partner by period, with the headline figures |
| `02_partner_share.png` | The partner against all other partners: its share and rank by period, and its growth against the total's |
| `03_competitors.png` | The reporter's largest partners, the partner in orange |
| `04_competitor_shares.png` | The shares of the partner and its five largest competitors by period |
| `05_prices.png` | Unit values: the partner, all partners together and the three largest competitors |
| `06_products.png` | The products traded with the partner |
| `07_partner_side.png` | The reporter in the partner's trade, and the partner's largest markets or suppliers |
| `08_both_reports.png` | COMTRADE only: the two countries' figures side by side |
| `09_other_direction.png` | The trade in both directions and the balance |
| `10_seasonality.png` | Monthly queries only: the trade with the partner by month |

The Word report has a numbered section for each of these, and `summary.md` gives the key findings, the key figures and the main tables.

### 9.9 BACI and COMTRADE: Strengths, Limits and Which to Use

Both databases come from the same reports, those countries send to the United Nations, but they use them differently. COMTRADE gives each country's own report. BACI, built by CEPII, combines the two reports of each flow (the exporter's and the importer's) into one figure. This section explains what that means for your results, including a limitation of BACI that you need to know before using its totals for one country.

**How BACI is built.** In CEPII's words (BACI page, last updated 30 January 2026): "Since countries report both their imports and their exports to the United Nations, the raw data we use may have duplicates flows". The two reports "should match, but in practice are virtually never identical", because "Import values are reported CIF (cost, insurance and freight) while exports are reported FOB (free on board)" and because "Mistakes are made, because of uncertainty on the final destination of exports, discrepancies in the classification of a given product, etc...". BACI then provides "a unique, reconciled trade flow": "CIF costs are estimated and removed from import values to compute FOB import values", and "The reliability of each country as a reporter of trade data is assessed", so that a less reliable reporter gets a lower weight.

A flow in BACI is one year, one exporter, one importer and one HS 6-digit product: the readme of version 202601 describes the files as "Trade flows at the year - exporter - importer - product level. Products in Harmonized System 6-digit nomenclature." According to CEPII's method paper, BACI provides a reconciled figure "for each flow reported at least by one of the partners", and "When only one of the reports is missing, the non missing declaration is used". Quantities reported in units other than tons are converted to tons using "implicit rates of conversion" that CEPII estimates. So BACI's figures are CEPII's estimates built from the two countries' reports; the analyzer uses them exactly as BACI gives them.

**The limitation: the same trade counted twice.** Because BACI pairs the two reports product by product, at the 6-digit level, it can only pair them when both countries put the goods under the same 6-digit code. When they use **different** codes, BACI sees two flows, each reported by one country only, and keeps both. Every total above 6 digits (a heading, a chapter, all products, and so every All-partners or partner total the analyzer builds from BACI) then counts that trade twice. It takes two conditions: both countries report the flow, and they classify it differently. Anyone who adds up BACI's rows gets the same totals; the analyzer neither causes nor corrects it. CEPII's documentation describes how each flow is reconciled, but no step that pairs reports filed under different codes, and the release notes of version 202601 (January 2026) list no such change.

**An example, from the source rows: wheat (HS `1001`) from the Russian Federation to Egypt.** Egypt declares its wheat imports as durum wheat (`100119`); Russia declares the same exports as other wheat (`100199`). In HS 1992, BACI's durum wheat is `100110` and its other wheat is `100190`. These are the two rows of the BACI file for 2020 (`BACI_HS92_Y2020_V202601.csv`; value `v` in thousand USD, quantity `q` in tons):

```
t,i,j,k,v,q
2020,643,818,100110,1950913.245,6845303.197
2020,643,818,100190,1796606.895,8254550.2
```

The first row is exactly Egypt's own COMTRADE report of its 2020 imports from Russia (code `100119`: 1,950.9 million USD, 6,845,303 t). The second is exactly Russia's own report of its 2020 exports to Egypt (code `100199`: 1,796.6 million USD, 8,254,550 t). They are two reports of the same trade, and BACI's total for `1001` adds them up:

| Year | Egypt's report (imports from Russia), million USD | Russia's report (exports to Egypt), million USD | BACI `1001`, million USD | BACI's total is |
|------|---:|---:|---:|---|
| 2015 | 1,080.8 | 841.6 | 841.6 | Russia's report only |
| 2016 | 1,118.3 | 988.6 | 2,106.9 | both reports added |
| 2017 | 1,597.9 | 1,433.5 | 3,031.4 | both reports added |
| 2018 | 2,053.6 | 1,893.3 | 3,946.9 | both reports added |
| 2019 | 1,432.8 | 1,273.6 | 2,706.5 | both reports added |
| 2020 | 1,950.9 | 1,796.6 | 3,747.5 | both reports added |
| 2021 | 1,820.5 | 1,552.6 | 3,371.7 | both reports added (Egypt's 6-digit records, 1,819.1, plus Russia's) |
| 2022 | 2,167.4 | not reported | 2,167.4 | Egypt's report only |
| 2023 | 2,560.3 | not reported | 2,560.3 | Egypt's report only |
| 2024 | 3,057.3 | not reported | 3,057.3 | Egypt's report only |

In 2015 the opposite happened: both countries reported some durum wheat, so BACI paired those two reports into one figure, and its durum row is Russia's 0.8 million USD; Egypt's 1,080.7 million USD of durum wheat from Russia does not appear in BACI at all. From 2022 Russia stopped reporting, so BACI has only Egypt's report. A growth rate or share computed from BACI across these years compares years counted once with years counted twice: from 2015 to 2016, for example, BACI's figure rises by 150%, while each country's own reports rise by 3.5% (Egypt's) and 17.5% (Russia's).

The same happens across Egypt's other wheat suppliers, so the All-partners totals are affected too:

| Year | Egypt's own report, all suppliers (COMTRADE), million USD | BACI, all suppliers, million USD | BACI / Egypt's report |
|------|---:|---:|---:|
| 2015 | 2,523.0 | 3,377.8 | 1.34 |
| 2016 | 2,238.5 | 4,069.2 | 1.82 |
| 2017 | 2,636.5 | 4,425.1 | 1.68 |
| 2018 | 2,787.7 | 4,967.3 | 1.78 |
| 2019 | 2,975.5 | 5,646.1 | 1.90 |

In tons, BACI's rows for 2018 add up to 22.1 million tons of wheat (9.5 million under durum, 12.5 million under other wheat), against 10.8 million tons in Egypt's own report (the weight on its 6-digit records, which UN Comtrade estimated; its record for `1001` itself has no weight). All figures are from BACI version 202601 and from COMTRADE, retrieved in October 2026. The first two queries of `batch_example.csv` are these BACI wheat queries: run the same queries with `--source comtrade` to see the difference for yourself.

**Valuation.** CEPII describes removing freight and insurance costs from import values. In version 202601, the BACI rows above that come from Egypt's reports equal Egypt's declared values exactly, and Egypt reports its imports CIF (COMTRADE's `cifvalue`). The release notes of version 202601 say only that the "Fobization process was simplified, with little effects on final outcome". We have not checked other flows.

**How common is it?** It needs a product that the two countries classify differently, which is most likely between sibling codes that customs cannot easily tell apart (durum and other wheat, for example) and for the residual "other" codes. It has been verified here for Egypt's wheat only; how widespread it is across BACI has not been measured. Where the two countries use the same codes, BACI's totals do not have this problem.

**How to spot it.** Every BACI report checks itself against COMTRADE. It sets BACI's total for each year beside the reporter's own COMTRADE figure for the same code and flow, partner World (and the partner, in a partner report), with the ratio of the two:
- The **COMTRADE check** sheet gives each year, with a note where COMTRADE has no figure (a year the reporter did not report, or an HS edition without the code).
- The checks on the About sheet and at the end of the Word report sum it up. For the first query of `batch_example.csv` (Egypt's wheat imports, 2015–2024) the line reads: "BACI's value is 1.07 to 1.90 times Egypt's own COMTRADE figure for 1001 in 2015–2024".
- No figure of the report uses the COMTRADE figures: they are only set beside BACI's. The check makes two COMTRADE requests for up to 12 years, and two more for each further 12, and needs an API key; without one, the report says the check was not made.

Where BACI's total is well above the reporter's own, look at its 6-digit rows (the **Products** sheet, or the partner report's Products sheet). Two sibling codes that each carry a large flow from the same partner are the sign of this limitation, though a genuine mix of both products looks the same.

**Which source to use.**

| You want | Use | Why |
|----------|-----|-----|
| One country's own imports or exports, especially totals at 4 digits and above | COMTRADE | Each figure is the country's own report, so nothing is counted twice; it matches the country's official statistics and has the latest years and monthly data |
| A country, or years, not reported to COMTRADE | BACI (often the only option) | BACI fills them in from the partners' reports: the Russian Federation's trade after 2021, for example |
| Consistent series from 1995 to 2024 at the 6-digit level | BACI | One classification (HS 1992) for every year, with no edition changes |
| Comparisons across many countries at the 6-digit level, or quantities and unit values comparable across countries | BACI | One figure per flow, all quantities in tons; CEPII states that BACI "was mostly designed for high disaggregated studies" |
| The two countries' own figures for the same trade | COMTRADE partner report | Both reports side by side, unadjusted (Section 9.8) |

COMTRADE has limits of its own: each country's classification choices stay as they are (Egypt's wheat appears as durum wheat), a country that has not reported a period has no figures for it, and two countries' reports of the same trade usually differ. The usual practice in trade statistics is to take one country's reports and stay with them, and to compare the two sides only at a level where their codes agree (here, the heading `1001`). The United Nations lists "improper declaration of product classification at the customs border, either entry or exit" among the known causes of differences between two countries' reports. A database that corrects misclassification before pairing the reports, as the OECD describes for its Balanced International Merchandise Trade Statistics, is the systematic remedy; the analyzer does not use such a database.

**References**
- CEPII, [BACI database page](https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37), last updated 30 January 2026.
- CEPII, [BACI release notes, version 202601](https://www.cepii.fr/DATA_DOWNLOAD/baci/doc/release_notes_202601.pdf), P. Cotterlaz, 22 January 2026; and the `Readme.txt` that comes with the BACI files.
- Gaulier, G. and Zignago, S. (2010). [BACI: International Trade Database at the Product-Level. The 1994-2007 Version](https://www.cepii.fr/CEPII/en/publications/wp/abstract.asp?NoDoc=2726). CEPII Working Paper 2010-23. The method paper CEPII asks BACI users to cite.
- United Nations Statistics Division (2019). [Guidelines on Analyzing and Reducing Bilateral Asymmetry](https://comtradeapi.un.org/files/v1/app/wiki/Guidelines_on_Analyzing_and_Reducing_Bilateral_Asymmetry-23_Apr_2019.pdf).
- OECD, [Balanced trade statistics](https://oecd.org/en/data/datasets/oecd-balanced-trade-statistics.html) (BIMTS).
- Valderas-Jaramillo, J. M., Rueda-Cantuche, J. M. and Ahmad, N. (2026). Why do trade statistics and national accounts' trade values differ? The role of misclassification of products. *Economic Systems Research*, 38(2), 275-292. [doi:10.1080/09535314.2026.2634802](https://doi.org/10.1080/09535314.2026.2634802).

---

## 10. Troubleshooting

### "Python is not recognized" error

This means Python was not added to your system PATH during installation.

**Solution**: Reinstall Python and make sure to check the box **"Add Python to PATH"** on the first installation screen.

### "No module named..." error

This means a required package is not installed.

**Solution**: Run the pip install command again (also needed after updating the analyzer):
```
pip install -r requirements.txt
```

### "Could not find a version that satisfies the requirement ..." during pip install

Your Python is newer than 3.14, and some of the packages are not yet available for it.

**Solution**: Install Python 3.14 (see Step 2.1) and run the pip install command again.

### "SUBSCRIPTION_KEY.env not found" error

The API credentials file is missing or misnamed. It is needed for COMTRADE queries only.

**Solution**: Create the file `SUBSCRIPTION_KEY.env` in the main folder as described in Step 5.2. If you created it with Notepad, check that it was not saved as `SUBSCRIPTION_KEY.env.txt`.

### "No trade recorded for this query" or "No data returned from COMTRADE API"

This could mean:
- The selected period/country/product combination has no trade
- The country has not reported this period to COMTRADE
- The BACI data files are not in the correct location
- The COMTRADE API is temporarily unavailable

**Solution**:
1. Verify the BACI files are in `data/BACI/BACI_HS92_V202601/`
2. Try a different period or product code
3. Check your internet connection for COMTRADE queries

### "Cannot write ... it is probably open in Excel or Word"

The workbook or the report from an earlier run of the same query is still open.

**Solution**: Close the file in Excel or Word and run the query again.

### Some years or months are Missing in a COMTRADE query

The country has not reported those periods to COMTRADE. The About and Data gaps sheets say which periods are affected.

**Solution**: The analyzer does not estimate them, so they stay Missing. You can choose a period the country has reported, use BACI for annual data, or add the figures from another source yourself.

### Many quantities are Missing in a BACI query

BACI leaves the quantity blank for some flows, sometimes for most of the trade in recent years.

**Solution**: Use value as the metric, or get the quantities from COMTRADE or another source. The Data gaps sheet lists each missing quantity with its value in million USD, so you can see how much of the trade it concerns.

### "A request hit the 250,000-record cap"

COMTRADE returns at most 250,000 records per request, so the data is incomplete. The checks in the About sheet then say **Complete download: NO**.

**Solution**: Narrow the query: choose fewer years or months, or a more specific product code.

### "... is not in BACI; use COMTRADE for this reporter"

BACI does not cover every country or territory.

**Solution**: Use COMTRADE for this country.

### BACI and COMTRADE list different subcategories for the same code

The two sources use different editions of the HS classification: BACI converts every year to HS 1992, while COMTRADE keeps each country's data in the edition it reported in. For example, `0401` has three subcategories in BACI and five in COMTRADE.

**Solution**: Nothing is wrong. [Section 9.4](#94-hs-editions) explains the editions and how to compare the two sources.

### Analysis runs but shows unexpected results

**Solution**:
- Verify you selected the correct trade direction (Imports vs Exports)
- Check that the product code is correct
- Try a different data source to compare results

---

## 11. License Information

This project is released under the **MIT License**.

### What does this mean?

The MIT License is one of the most permissive open-source licenses. It means:

**You CAN:**
- Use this software for any purpose - personal, educational, or commercial
- Modify the source code to suit your needs
- Distribute copies to others
- Include it in your own projects (even commercial ones)
- Use it without paying any fees

**You MUST:**
- Include the original copyright notice and license text in any copies or substantial portions of the software

**You CANNOT:**

- Hold the author liable for any issues arising from the use of this software
- Claim that you wrote the original software

In simple terms: **Use it freely, give credit where due, and don't blame me if something goes wrong!**

---

## 12. Contact and Support

### Author

**Moamen Abdelkawy**

### Get in Touch

- **Email**: [moamen.abdelkawy@outlook.com](mailto:moamen.abdelkawy@outlook.com)

### Reporting Issues

If you encounter any bugs or have suggestions for improvements, please:

1. **Email me** with a description of the issue
2. Include:
   - What you were trying to do
   - What happened instead
   - Any error messages you saw
   - Your operating system (Windows/macOS/Linux)

### Feature Requests

Have an idea for a new feature? I'd love to hear it! Send me an email describing:
- What feature you'd like to see
- How it would help your work
- Any examples of similar features in other tools

---

## Quick Reference Card

### Starting the Analyzer

```bash
# Interactive (on macOS, type python3 instead of python)
python trade_analyzer.py

# One query from the command line
python trade_analyzer.py --source baci --reporter Egypt --product 1001 --flow M --period 2015-2024

# Many queries from a CSV file
python trade_analyzer.py --batch batch_example.csv

# Once: convert BACI for fast queries
python trade_analyzer.py --build-baci-cache

# Refresh the US CPI table used for constant dollars
python trade_analyzer.py --update-cpi
```

### Common Inputs

| Prompt | Options |
|--------|---------|
| Frequency | `A` (Annual) or `M` (Monthly) |
| Data Source | `B` (BACI) or `C` (COMTRADE) |
| Period | `2023` or `2018-2023`; monthly: `202312` or `202301-202312` |
| Country | Name (`Egypt`) or Code (`818`) |
| Product | `10`, `1001`, `100190`, `TOTAL`, `AG2`, `AG4`, `AG6` |
| Direction | `M` (Imports) or `X` (Exports) |
| Partners | `A` (All) or `S` (a report on the trade with one partner) |
| Metric | BACI: `V` (Value) or `Q` (Quantity); COMTRADE: from the list shown |

### File Locations

| File Type | Location |
|-----------|----------|
| BACI Data | `data/BACI/BACI_HS92_V202601/` |
| BACI Fast Cache | `data/BACI/BACI_HS92_V202601/parquet/` |
| Country Codes | `data/meta/country_codes_V202601.csv` |
| Product Codes | `data/meta/product_codes_HS92_V202601.csv` |
| US CPI Table | `data/meta/us_cpi_worldbank.csv` |
| HS Edition Table | `data/meta/hs_editions.csv` |
| API Credentials | `SUBSCRIPTION_KEY.env` |
| Batch Example | `batch_example.csv` |
| Results | `output/<query folder>/` |

---

## Citation

If you use this tool in your research, please consider citing it:

```
Abdelkawy, M. (2026). International Trade Analyzer [Computer software].
https://github.com/Moamen-Abdelkawy/InternationalTradeAnalyzer
```

---

*Thank you for using the International Trade Analyzer!*

*Last updated: October 2026*
