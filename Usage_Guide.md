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
- At least **3 GB of free disk space** (for the BACI database)
- A web browser

---

## 2. Installing Python

Python is a programming language that this tool is built with. You need to install it on your computer.

### Step 2.1: Download Python

1. Open your web browser and go to: **https://www.python.org/downloads/**

2. Click the large yellow button that says **"Download Python 3.x.x"** (the exact version number may vary)

   ![Python Download Page](https://www.python.org/static/img/python-logo.png)

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

---

## 3. Downloading the Repository

A "repository" (or "repo") is simply a folder containing all the project files. There are two ways to download it:

### Option A: Download as ZIP (Easiest - No Git Required)

1. Go to: **https://github.com/MoamenAbdelkawy/InternationalTradeAnalyzer**

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
git clone https://github.com/MoamenAbdelkawy/InternationalTradeAnalyzer.git
```

---

## 4. Setting Up the BACI Database

The BACI database provides harmonized bilateral trade data. It's a large file that needs to be downloaded separately.

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

To access real-time trade data from the UN COMTRADE database, you need a free API key.

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

1. Open the International Trade Analyzer folder

2. Find the file named `SUBSCRIPTION_KEY.env`

3. Open this file with a **text editor**:
   - **Windows**: Right-click the file > **Open with** > **Notepad**
   - **macOS**: Right-click the file > **Open With** > **TextEdit**

4. You will see content like this:
   ```
   # comtrade - v1 API Credentials
   # Enter your credentials inside the double quotes
   
   COMTRADE_USERNAME="Your COMTRADE Username Here"
   PRIMARY_KEY="Your Primary Key"
   SECONDARY_KEY="Your Secondary Key"
   ```
   
5. Fill in your credentials **between the double quotes**. For example:
   
   ```
   # comtrade - v1 API Credentials
   COMTRADE_USERNAME="john.smith@email.com"
   PRIMARY_KEY="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
   SECONDARY_KEY="p6o5n4m3l2k1j0i9h8g7f6e5d4c3b2a1"
   ```
   
6. **Save the file** and close the text editor

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

---

## 7. Running the Analyzer

Now you're ready to run the analyzer!

### Step 7.1: Start the Analyzer

With the terminal still open in the International Trade Analyzer folder, type:

#### On Windows:
```
python trade_analyzer.py
```

#### On macOS:
```
python3 trade_analyzer.py
```

Press **Enter** and the analyzer will start!

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

- **BACI**: Uses the downloaded database (1995-2024), data is harmonized
- **COMTRADE**: Uses the API for real-time data (1962-present)

### Step 8.3: Period Selection

Enter the year(s) you want to analyze:
- Single year: `2023`
- Year range: `2018-2023`

### Step 8.4: Reporter Country

Enter the country whose trade you want to analyze:
- By name: `Egypt`, `United States`, `China`
- By code: `818` (Egypt), `842` (USA), `156` (China)

Reference: Country codes can be found in `data/meta/country_codes_V202601.csv`

### Step 8.5: Product Code

Enter the HS product code:
- 2-digit chapter: `10` (Cereals)
- 4-digit heading: `1001` (Wheat)
- 6-digit subheading: `100190` (Wheat, other)

Reference: Product codes can be found in `data/meta/product_codes_HS92_V202601.csv`

### Step 8.6: Trade Direction

- `M` or `Imports`: Goods coming INTO the reporter country
- `X` or `Exports`: Goods going OUT of the reporter country

### Step 8.7: Partner Selection

- `A` or `All`: Analyze trade with all partners (shows top trading partners)
- `S` or `Specific`: Analyze trade with one specific partner country

### Step 8.8: Metric Selection

Choose how to rank trading partners. For BACI, these will be:
- `V` or `Value`: Trade value in USD
- `Q` or `Quantity`: Quantity traded

For COMTRADE, the available metrics differe according to the chosen product(s).

**Note**: The selected metric is used for ranking. All available metrics are included in the CSV output.

---

## 9. Understanding the Output

After the analysis runs, you'll find output files in the `output` folder:

### CSV Files (.csv)

- Contains detailed trade data in spreadsheet format
- Can be opened with Excel, Google Sheets, or any spreadsheet software
- Includes ALL available metrics, sorted by your chosen metric
- Example: `AllPartners_Egypt_imp_HS10_Val.csv`

### Summary Files (.txt)

- Text summaries of the analysis
- Human-readable reports with key statistics
- Example: `AllPartners_Egypt_imp_HS10_Val_Summary.txt`

### Visualization Files (.png)

- Bar charts showing top trading partners
- Stacked bar charts for partner analysis over time
- Can be included in reports or presentations
- Example: `BarChart_Egypt_imp_HS10_Val.png`

---

## 10. Troubleshooting

### "Python is not recognized" error

This means Python was not added to your system PATH during installation.

**Solution**: Reinstall Python and make sure to check the box **"Add Python to PATH"** on the first installation screen.

### "No module named..." error

This means a required package is not installed.

**Solution**: Run the pip install command again:
```
pip install -r requirements.txt
```

### "SUBSCRIPTION_KEY.env not found" error

The API credentials file is missing or misnamed.

**Solution**: Make sure the file `SUBSCRIPTION_KEY.env` exists in the main folder and contains your API credentials.

### "No data found" message

This could mean:
- The BACI data files are not in the correct location
- The selected year/country/product combination has no data
- The COMTRADE API is temporarily unavailable

**Solution**:
1. Verify the BACI files are in `data/BACI/BACI_HS92_V202601/`
2. Try a different year or product code
3. Check your internet connection for COMTRADE queries

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
# Windows
python trade_analyzer.py

# macOS
python3 trade_analyzer.py
```

### Common Inputs

| Prompt | Options |
|--------|---------|
| Frequency | `A` (Annual) or `M` (Monthly) |
| Data Source | `B` (BACI) or `C` (COMTRADE) |
| Period | `2023` or `2018-2023` |
| Country | Name (`Egypt`) or Code (`818`) |
| Product | `10`, `1001`, `100190`, `TOTAL` |
| Direction | `M` (Imports) or `X` (Exports) |
| Partners | `A` (All) or `S` (Specific) |
| Metric | `V` (Value) or `Q` (Quantity) |

### File Locations

| File Type | Location |
|-----------|----------|
| BACI Data | `data/BACI/BACI_HS92_V202601/` |
| Country Codes | `data/meta/country_codes_V202601.csv` |
| Product Codes | `data/meta/product_codes_HS92_V202601.csv` |
| API Credentials | `SUBSCRIPTION_KEY.env` |
| Output Files | `output/` |

---

## Citation

If you use this tool in your research, please consider citing it:

```
Abdelkawy, M. (2026). International Trade Analyzer [Computer software].
https://github.com/MoamenAbdelkawy/InternationalTradeAnalyzer
```

---

*Thank you for using the International Trade Analyzer!*

*Last updated: February 2026*
