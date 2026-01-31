# UN Comtrade API Package
This package simplifies calling [APIs of UN Comtrade](https://comtradedeveloper.un.org) to extract and download data
 (and much more).

# Interactive Trade Data Extraction Tool

## NEW: `comtrade_trade_analysis.py` - Interactive CLI Tool
An interactive command-line tool for extracting and analyzing trade data from UN COMTRADE API. This tool is located in the **parent directory** and provides a user-friendly interface similar to the BACI trade analysis tool.

### Features
- **Interactive prompts** for all parameters (no coding required)
- **Flexible period selection** (annual or monthly data)
- **Multiple metrics support** (trade value, net weight, gross weight, quantity, etc.)
- **Automatic aggregation** by trading partner
- **CSV export** with descriptive filenames and totals
- **Real-time data** from UN COMTRADE API

### Quick Start
```bash
python comtrade_trade_analysis.py
```

### What the Tool Does
1. Loads API credentials from `SUBSCRIPTION_KEY.env`
2. Asks for data frequency (Annual or Monthly)
3. Asks for time period(s)
4. Asks for product classification (HS, SITC, etc.)
5. Asks for reporter country
6. Asks for product code(s)
7. Asks for trade direction (Imports/Exports)
8. Fetches data from UN COMTRADE API
9. Aggregates data by trading partner
10. Asks for ranking metric (value, weight, quantity, etc.)
11. Exports results to CSV with summary statistics

### Example Usage

**Example 1: Egypt's Annual Bovine Imports in 2023**
- Frequency: `A` (Annual)
- Period: `2023`
- Classification: `HS`
- Reporter: `Egypt` or `818`
- Product: `0102`
- Direction: `imports`
- Ranking: `1` (Trade Value)

**Output:** `COMTRADE_Annual_2023_Egypt_imp_0102.csv`

**Example 2: USA Monthly Wheat Exports (Jan-Mar 2024)**
- Frequency: `M` (Monthly)
- Period: `202401,202402,202403`
- Classification: `HS`
- Reporter: `USA`
- Product: `1001`
- Direction: `exports`
- Ranking: Select from available metrics

### Setup Requirements
1. **API Subscription Key:** Ensure `SUBSCRIPTION_KEY.env` exists in the parent directory with:
   ```
   PRIMARY_KEY="your_api_key_here"
   ```
2. **Python Package:** Install comtradeapicall:
   ```bash
   pip install comtradeapicall
   ```
3. **Dependencies:** pandas, python-dotenv
   ```bash
   pip install pandas python-dotenv
   ```

### Key Differences from BACI Tool
| Feature | BACI Tool | COMTRADE Tool |
|---------|-----------|---------------|
| Data Source | Pre-downloaded CSV files | Live API calls |
| Data Recency | Up to 2023 (periodic updates) | Real-time, most current |
| Classification | HS02 only | HS, SITC, BEC, and more |
| Granularity | Annual only | Annual or Monthly |
| Metrics | Value & Quantity | Value, Net/Gross Weight, Quantity, CIF, FOB |
| Internet Required | No | Yes |
| API Subscription | No | Yes (free tier available) |

### Output Format
**CSV File Naming:**
`COMTRADE_{Frequency}_{Period}_{Reporter}_{Direction}_{Product}.csv`

Examples:
- `COMTRADE_Annual_2023_Egypt_imp_0102.csv`
- `COMTRADE_Monthly_202401_202402_202403_USA_exp_1001.csv`

**CSV Columns** (vary based on available metrics):
- `Partner_Code` - Trading partner country code
- `Partner_Name` - Trading partner country name
- `Trade_Value_USD` - Trade value in USD
- `Net_Weight_Kg` - Net weight in kilograms
- `Gross_Weight_Kg` - Gross weight in kilograms
- `Quantity` - Quantity (unit varies by product)
- `CIF_Value_USD` - CIF value (imports)
- `FOB_Value_USD` - FOB value (exports)

**Features:**
- Results sorted by selected metric (greatest to smallest)
- TOTAL row at bottom with sum of all numeric columns
- Ready for analysis in Excel or Python

### Tips & Best Practices

1. **Choosing Frequency:**
   - Use **Annual** for long-term trends and historical analysis
   - Use **Monthly** for recent data and seasonal patterns

2. **Period Selection:**
   - Annual: Can query multiple years (e.g., `2020,2021,2022`)
   - Monthly: Use YYYYMM format (e.g., `202312` for Dec 2023)
   - **Tip:** Start with single period, expand if needed

3. **Product Codes:**
   - `TOTAL` - All products
   - `AG2` - All 2-digit aggregated
   - `AG4` - All 4-digit aggregated
   - Specific codes: `0102`, `1001`, etc.
   - Multiple codes: `0102,0201,0202`

4. **Classification Selection:**
   - **HS** (Harmonized System) - Most common, recommended for goods
   - **SITC** - Standard International Trade Classification
   - **BEC** - Broad Economic Categories

5. **API Rate Limits:**
   - Free tier: Limited requests per hour
   - Premium: Higher limits
   - Tool handles errors and provides clear messages

6. **Ranking Metrics:**
   - **Trade Value** - Monetary worth (most common)
   - **Net Weight** - For volume-based analysis
   - **Quantity** - For unit-based analysis

### Troubleshooting

**"API credentials not found"**
- Ensure `SUBSCRIPTION_KEY.env` exists in parent directory
- Check that `PRIMARY_KEY` is set correctly

**"No data returned from API"**
- Country may not have data for selected period/product
- Try different period or product code
- Check if reporter has submitted data to COMTRADE

**"Rate limit exceeded"**
- Wait a few minutes before retrying
- Consider upgrading to premium API subscription
- Reduce number of periods in single query

**"Invalid classification code"**
- Ensure you're using supported codes: HS, S1-S4, B4, B5
- Not all countries report all classifications

### Comparison: When to Use Which Tool?

**Use BACI Tool (`baci_trade_analysis.py`) when:**
- Working with historical data (2002-2023)
- Need offline analysis (no internet required)
- Want reconciled, cleaned bilateral trade flows
- Analyzing long-term trends across many years
- No API subscription available

**Use COMTRADE Tool (`comtrade_trade_analysis.py`) when:**
- Need most recent/current data
- Want multiple metrics (weight, CIF/FOB values, etc.)
- Need monthly granularity
- Want to use different classifications (SITC, BEC, etc.)
- Have API subscription
- Need real-time or frequently updated data

---

## NEW: `comtrade_timeseries_analysis.py` - Time Series Analysis Tool

An interactive command-line tool for analyzing **trade trends over time**. This tool is located in the **parent directory** and provides year-by-year trade data for time series analysis and visualization.

### Features
- **Time series analysis** - Track trade trends year by year
- **Two analysis modes:**
  1. Total trade (all partners combined) over time
  2. Trade with specific partner over time
- **Year-by-year data** from 1962 to present
- **Multiple metrics** (trade value, weights, quantity, etc.)
- **CSV export** optimized for visualization and trend analysis
- **Real-time data** from UN COMTRADE API

### Quick Start
```bash
python comtrade_timeseries_analysis.py
```

### What the Tool Does
1. Loads API credentials from `SUBSCRIPTION_KEY.env`
2. Asks for time period (e.g., `2010-2024`)
3. Asks for product classification (HS, SITC, etc.)
4. Asks for reporter country
5. Asks for product code
6. Asks for trade direction (Imports/Exports)
7. Asks for analysis type:
   - **Total**: All partners combined (see overall trend)
   - **Specific partner**: Trade with one country (bilateral trend)
8. Fetches data year by year from UN COMTRADE API
9. Aggregates data by year
10. Exports time series to CSV

### Example Usage

**Example 1: Egypt's Total Wheat Imports Over Time (2010-2024)**
- Period: `2010-2024`
- Classification: `HS`
- Reporter: `Egypt` or `818`
- Product: `1001`
- Direction: `imports`
- Analysis: `1` (Total - all partners)

**Output:** `COMTRADE_TimeSeries_Egypt_imp_1001_Total_All_Partners.csv`

| Year | Trade_Value_USD | Net_Weight_Kg | Gross_Weight_Kg | Quantity |
|------|----------------|---------------|-----------------|----------|
| 2010 | $2,500,000,000 | 5,200,000,000 | 0.00 | 5,200,000,000 |
| 2011 | $2,800,000,000 | 5,600,000,000 | 0.00 | 5,600,000,000 |
| ... | ... | ... | ... | ... |

**Example 2: Egypt's Wheat Imports from Russia Over Time (2015-2024)**
- Period: `2015-2024`
- Classification: `HS`
- Reporter: `Egypt` or `818`
- Product: `1001`
- Direction: `imports`
- Analysis: `2` (Specific partner)
- Partner: `Russia` or `643`

**Output:** `COMTRADE_TimeSeries_Egypt_imp_1001_Russian_Federation.csv`

### Use Cases

**Use this tool when you want to:**
- **Track trends** - See how trade volumes/values change over time
- **Identify patterns** - Detect seasonal patterns, growth trends, or disruptions
- **Compare periods** - Analyze before/after scenarios (e.g., policy changes, events)
- **Bilateral analysis** - Track trade relationship with specific partner
- **Visualization** - Create charts and graphs (data optimized for Excel/Python plotting)
- **Research** - Academic or business research requiring historical trade data

### Output Format

**CSV File Naming:**
- Total analysis: `COMTRADE_TimeSeries_{Reporter}_{Direction}_{Product}_Total_All_Partners.csv`
- Partner analysis: `COMTRADE_TimeSeries_{Reporter}_{Direction}_{Product}_{Partner}.csv`

**CSV Columns** (vary based on available metrics):
- `Year` - Year of trade
- `Trade_Value_USD` - Trade value in USD
- `Net_Weight_Kg` - Net weight in kilograms
- `Gross_Weight_Kg` - Gross weight in kilograms
- `Quantity` - Quantity (unit varies by product)
- `CIF_Value_USD` - CIF value (imports)
- `FOB_Value_USD` - FOB value (exports)

**Features:**
- One row per year
- Sorted chronologically
- Ready for plotting in Excel, Python, R, etc.
- Includes all available metrics from COMTRADE

### Tips & Best Practices

1. **Period Selection:**
   - Choose periods based on your analysis needs
   - Longer periods (10+ years) - long-term trends
   - Shorter periods (3-5 years) - recent changes
   - Consider data availability (earlier years may be sparse)

2. **Analysis Type:**
   - **Total (all partners)** - Overall country trade performance
   - **Specific partner** - Bilateral trade relationship analysis

3. **Data Visualization:**
   - Import CSV into Excel and create line charts
   - Use Python (matplotlib, plotly) for advanced visualizations
   - Compare multiple time series (run tool multiple times)

4. **Combining with Other Tools:**
   - Use `comtrade_trade_analysis.py` to see partner breakdown for specific years
   - Use time series tool to identify years of interest
   - Deep dive into specific years with the trade analysis tool

### Comparison: Time Series vs Trade Analysis Tools

| Feature | Time Series Tool | Trade Analysis Tool |
|---------|------------------|---------------------|
| **Purpose** | Track trends over time | Analyze partners for specific period |
| **Output** | Year-by-year data | Partner-by-partner data |
| **Time Dimension** | Multiple years (1 row per year) | Single period or aggregated |
| **Partner Dimension** | Single partner or all combined | All partners listed |
| **Best For** | Trend analysis, visualization | Partner comparison, rankings |
| **Use Case Example** | "How did imports change 2010-2024?" | "Who were top partners in 2023?" |

### Example Workflow

1. **Identify trend** with time series tool:
   - Run: Egypt wheat imports (total) 2010-2024
   - Notice spike in 2022

2. **Deep dive** with trade analysis tool:
   - Run: Egypt wheat imports for 2022
   - See which partners contributed to spike

3. **Track specific relationship** with time series tool:
   - Run: Egypt wheat imports from Russia 2010-2024
   - Analyze bilateral trade pattern

 # Revision
 - 1.3.0: Add a function to extract Trade Matrix (the official trade statistics complemented by estimates)
 - 1.2.3: Add functions to download and combine bulk files (bulkDownloadAndCombineFinalFile)
 - 1.2.2: Removed AIS function as it is no longer available; Add functions getTradeBalance and getBilateralData

## Details
[UN Comtrade](https://comtrade.un.org) provides free and premium APIs to extract and download data/metadata, however
 it is quite a learning curve to understand all of APIs end-points and parameters. This package simplifies it by
  calling a single python function with the appropriate parameters. Learn more about UN Comtrade at the [UN Comtrade Docs](https://uncomtrade.org/docs).

This project is intended to be deployed at [The Python Package Index](https://pypi.org/project/comtradeapicall/), therefore the structure of
 folders follows the suggested layout from [Packaging Python Project](https://packaging.python.org/en/latest/tutorials/packaging-projects/). The main scripts are located at **/src/comtradeapicall/**. And the folder **tests** and **examples** contains the example scripts how to install and use the package.

 This package is provided ‘as is’ without any warranties or guarantees of any kind, whether express or implied, including but not limited to implied warranties of merchantability or fitness for a particular purpose. No support or maintenance is promised or provided
 
 ## Prerequisites
This package assumes using Python 3.7 and the expected package dependencies are listed in the "requirements.txt" file
 for PIP, you need to run the following command to get dependencies:
```
pip install -r requirements.txt
```

## Installing the package (from PyPi)
The package has been deployed to the PyPi and it can be install using pip command below:
```
pip install comtradeapicall
```

## Components
- **Get/Preview:** Model class to extract the data into pandas data frame
  - previewFinalData(**SelectionCriteria**, **query_option**) : return data frame containing final trade data (limited to 500 records)
  - previewTarifflineData(**SelectionCriteria**, **query_option**) : return data frame containing tariff line data (limited to 500
   records)
  - getFinalData(**subscription_key**, **SelectionCriteria**, **query_option**) : return data frame containing final
   trade data (limited to 250K records)
  - getTarifflineData(**subscription_key**, **SelectionCriteria**, **query_option**)  : return data frame containing
   tariff line data (limited to 250K records)
  - Alternative functions of _previewFinalData, _previewTarifflineData, _getFinalData, _getTarifflineData returns the
   same data frame, respectively,  with query optimization by calling multiple APIs based on the periods (instead of
    single API call)
  - previewCountFinalData(**SelectionCriteria**, **query_option**) : return data frame containing actual count of trade data (no subscription key, but limited to 500 records)
  - getCountFinalData(**subscription_key**,**SelectionCriteria**, **query_option**) : return data frame containing actual count of trade data (with subscription key)    
  - getTradeBalance(**subscription_key**,**SelectionCriteria**, **query_option**) : return data frame with trade balance indicator
  - getBilateralData(**subscription_key**,**SelectionCriteria**, **query_option**) : return data frame by comparing reported data with their mirror (data reported by the trading partners)

  
- **DataAvailability:** Model class to extract data availability
  - _getFinalDataAvailability(**SelectionCriteria**) : return data frame containing final data
   availability - no subscription key
  - getFinalDataAvailability(**subscription_key**, **SelectionCriteria**) : return data frame containing final data
   availability
  - _getTarifflineDataAvailability(**SelectionCriteria**) : return data frame containing tariff
   line
   data
   availability - no subscription key
  - getTarifflineDataAvailability(**subscription_key**, **SelectionCriteria**) : return data frame containing tariff
   line
   data
   availability
  - getFinalDataBulkAvailability(**subscription_key**, **SelectionCriteria**, **[publishedDateFrom]**, **[publishedDateTo]**) : return data frame containing final bulk files data
   availability
  - getTarifflineDataBulkAvailability(**subscription_key**, **SelectionCriteria**, **[publishedDateFrom]**, **[publishedDateTo]**) : return data frame containing tariff
   line bulk files 
   data
   availability
  - getLiveUpdate(**subscription_key**) : return data frame recent data releases
  
- **BulkDownload:** Model class to download the data files
  - bulkDownloadFinalFile(**subscription_key**, **directory**,  **SelectionCriteria**, **decompress**, **[publishedDateFrom]**, **[publishedDateTo]**) : download/save
   final data files to specified folder
  - bulkDownloadFinalClassicFile(**subscription_key**, **directory**,  **SelectionCriteria**, **decompress**, **[publishedDateFrom]**, **[publishedDateTo]**) : download/save
   final classic data files to specified folder 
  - bulkDownloadTarifflineFile(**subscription_key**, **directory**,  **SelectionCriteria**, **decompress**, **[publishedDateFrom]**, **[publishedDateTo]**) : download
  /save tariff line data files to specified folder
  - bulkDownloadAndCombineTarifflineFile(**subscription_key**, **directory**,  **SelectionCriteria**, **decompress**, **[publishedDateFrom]**, **[publishedDateTo]**) : download
  /save and combine tariff line data files (into a single file) to specified folder
  - bulkDownloadAndCombineFinalFile(**subscription_key**, **directory**,  **SelectionCriteria**, **decompress**, **[publishedDateFrom]**, **[publishedDateTo]**) : download
  /save and combine final data files (into a single file) to specified folder  
  - bulkDownloadAndCombineFinalClassicFile(**subscription_key**, **directory**,  **SelectionCriteria**, **decompress**, **[publishedDateFrom]**, **[publishedDateTo]**) : download
  /save and combine final classic data files (into a single file) to specified folder 

- **Async:** Model class to extract the data asynchronously (limited to 2.5M records) with email notification
  - submitAsyncFinalDataRequest(**subscription_key**, **SelectionCriteria**, **query_option**) : submit a final data job
  - submitAsyncTarifflineDataRequest(**subscription_key**, **SelectionCriteria**, **query_option**) : submit a tariff line data job
  - checkAsyncDataRequest(**subscription_key**, **[batchId]**) : check status of submitted job
  - downloadAsyncFinalDataRequest(**subscription_key**, **directory**, **SelectionCriteria**, **query_option**) : submit, wait and download the resulting final file
  - downloadAsyncTarifflineDataRequest(**subscription_key**, **directory**, **SelectionCriteria**, **query_option**) : submit, wait and download the resulting  tariff line file
 
- **Metadata:** Model class to extract metadata and publication notes
  - _getMetadata(**SelectionCriteria**, **showHistory**) : return data frame with metadata and publication notes - no subscription key
  - getMetadata(**subscription_key**, **SelectionCriteria**, **showHistory**) : return data frame with metadata and publication notes
  - listReference(**[category]**) : return data frame containing list of references
  - getReference(**category**) : return data frame with the contents of specific references

- **SUV:** Model class to extract data on Standard Unit Values (SUV) and their ranges
  - getSUV(**subscription_key**, **SelectionCriteria**, **[qtyUnitCode]**) : return data frame with SUV data

See differences between final and tariff line data at the [Docs](https://uncomtrade.org/docs/what-is-tariffline-data/)
 
## Selection Criteria
- typeCode(str) : Product type. Goods (C) or Services (S)
- freqCode(str) : The time interval at which observations occur. Annual (A) or Monthly (M)
- clCode(str) : Indicates the product classification used and which version (HS, SITC)
- period(str) :  Combination of year and month (for monthly), year for (annual)
- reporterCode(str) : The country or geographic area to which the measured statistical phenomenon relates
- cmdCode(str) : Product code in conjunction with classification code
- flowCode(str) : Trade flow or sub-flow (exports, re-exports, imports, re-imports, etc.)
- partnerCode(str) : The primary partner country or geographic area for the respective trade flow
- partner2Code(str) : A secondary partner country or geographic area for the respective trade flow
- customsCode(str) : Customs or statistical procedure
- motCode(str) : The mode of transport used when goods enter or leave the economic territory of a country

## Query Options
- maxRecords(int) : Limit number of returned records
- format_output(str) : The output format. CSV or JSON 
- aggregateBy(str) : Option for aggregating the query 
- breakdownMode(str) : Option to select the classic (trade by partner/product) or plus (extended breakdown) mode
- countOnly(bool) : Return the actual number of records if set to True 
- includeDesc(bool) : Option to include the description or not

## Proxy Server
- proxy_url(str) : All functions that call the API support the proxy server. Use the parameter proxy_url.

 
## Examples of python usage
- Extract Australia imports of commodity code 91 in classic mode in May 2022
``` python
mydf = comtradeapicall.previewFinalData(typeCode='C', freqCode='M', clCode='HS', period='202205',
                                        reporterCode='36', cmdCode='91', flowCode='M', partnerCode=None,
                                        partner2Code=None,
                                        customsCode=None, motCode=None, maxRecords=500, format_output='JSON',
                                        aggregateBy=None, breakdownMode='classic', countOnly=None, includeDesc=True)
```    
- Extract Australia tariff line imports of commodity code started with 90 and 91 from Indonesia in May 2022
``` python
mydf = comtradeapicall.previewTarifflineData(typeCode='C', freqCode='M', clCode='HS', period='202205',
                                             reporterCode='36', cmdCode='91,90', flowCode='M', partnerCode=36,
                                             partner2Code=None,
                                             customsCode=None, motCode=None, maxRecords=500, format_output='JSON',
                                             countOnly=None, includeDesc=True)
```    
- Extract Australia imports of commodity codes 90 and 91 from all partners in classic mode in May 2022
``` python
mydf = comtradeapicall.getFinalData(subscription_key, typeCode='C', freqCode='M', clCode='HS', period='202205',
                                    reporterCode='36', cmdCode='91,90', flowCode='M', partnerCode=None,
                                    partner2Code=None,
                                    customsCode=None, motCode=None, maxRecords=2500, format_output='JSON',
                                    aggregateBy=None, breakdownMode='classic', countOnly=None, includeDesc=True)
```    
- Extract Australia tariff line imports of commodity code started with 90 and 91 from Indonesia in May 2022
``` python
mydf = comtradeapicall.getTarifflineData(subscription_key, typeCode='C', freqCode='M', clCode='HS', period='202205',
                                         reporterCode='36', cmdCode='91,90', flowCode='M', partnerCode=36,
                                         partner2Code=None,
                                         customsCode=None, motCode=None, maxRecords=2500, format_output='JSON',
                                         countOnly=None, includeDesc=True)
```  
- Download monthly France final data of Jan-2000
``` python
comtradeapicall.bulkDownloadFinalFile(subscription_key, directory, typeCode='C', freqCode='M', clCode='HS',
                                      period='200001', reporterCode=251, decompress=True)
```  
- Download monthly France tariff line data of Jan-March 2000
``` python
comtradeapicall.bulkDownloadTarifflineFile(subscription_key, directory, typeCode='C', freqCode='M', clCode='HS',
                                           period='200001,200002,200003', reporterCode=504, decompress=True)
```  
- Download annual Morocco tariff line  data of 2010
``` python
comtradeapicall.bulkDownloadTarifflineFile(subscription_key, directory, typeCode='C', freqCode='A', clCode='HS',
                                           period='2010', reporterCode=504, decompress=True)
```  
- Download all final annual data  in HS classification released yesterday
``` python
yesterday = date.today() - timedelta(days=1)
comtradeapicall.bulkDownloadTarifflineFile(subscription_key, directory, typeCode='C', freqCode='A', clCode='HS',
                                              period=None, reporterCode=None, decompress=True,
                                              publishedDateFrom=yesterday, publishedDateTo=None)
```  
- Show the recent releases
``` python
mydf = comtradeapicall.getLiveUpdate(subscription_key)
```  
- Extract final data availability in 2021
``` python
mydf = comtradeapicall.getFinalDataAvailability(subscription_key, typeCode='C', freqCode='A', clCode='HS',
                                                         period='2021', reporterCode=None)
```  
- Extract tariff line data availability in June 2022
``` python
mydf = comtradeapicall.getTarifflineDataAvailability(subscription_key, typeCode='C', freqCode='M', clCode='HS',
                                                        period='202206', reporterCode=None)
``` 
- Extract final bulk files data availability in 2021 for the SITC Rev.1 classification
``` python
mydf = comtradeapicall.getFinalDataBulkAvailability(subscription_key, typeCode='C', freqCode='A', clCode='S1',
                                                         period='2021', reporterCode=None)
``` 
- Extract tariff line bulk files data availability in June 2022
``` python
mydf = comtradeapicall.getTarifflineDataBulkAvailability(subscription_key, typeCode='C', freqCode='M', clCode='HS',
                                                        period='202206', reporterCode=None)
``` 
- List data availabity from last week for reference year 2021
``` python
mydf = comtradeapicall.getFinalDataAvailability(subscription_key, typeCode='C', freqCode='A', clCode='HS',period='2021', reporterCode=None, publishedDateFrom=lastweek, publishedDateTo=None)
``` 
- List tariffline data availabity from last week for reference period June 2022
``` python
mydf = comtradeapicall.getTarifflineDataAvailability(subscription_key, typeCode='C', freqCode='M',
                                                        clCode='HS',
                                                        period='202206', reporterCode=None, publishedDateFrom=lastweek, publishedDateTo=None)
``` 
- List bulk data availability for SITC Rev.1 for reference year 2021 released since last week
``` python
mydf = comtradeapicall.getFinalDataBulkAvailability(subscription_key, typeCode='C', freqCode='A',
                                                    clCode='S1',
                                                    period='2021', reporterCode=None, publishedDateFrom=lastweek, publishedDateTo=None)
``` 
- List bulk tariffline data availability from last week for reference period June 2022
``` python
mydf = comtradeapicall.getTarifflineDataBulkAvailability(subscription_key, typeCode='C', freqCode='M',
                                                            clCode='HS',
                                                            period='202206', reporterCode=None, publishedDateFrom=lastweek, publishedDateTo=None)

``` 
- Obtain all metadata and publication notes for May 2022
``` python
mydf = comtradeapicall.getMetadata(subscription_key, typeCode='C', freqCode='M', clCode='HS', period='202205',
                                                 reporterCode=None, showHistory=True)
``` 
- Submit asynchronous final data request
``` python
myJson = comtradeapicall.submitAsyncFinalDataRequest(subscription_key, typeCode='C', freqCode='M', clCode='HS',
                                    period='202205',
                                    reporterCode='36', cmdCode='91,90', flowCode='M', partnerCode=None,
                                    partner2Code=None,
                                    customsCode=None, motCode=None, aggregateBy=None, breakdownMode='classic')
print("requestID: ",myJson['requestId'])
``` 
- Submit asynchronous tariff line data request
``` python
myJson = comtradeapicall.submitAsyncTarifflineDataRequest(subscription_key, typeCode='C', freqCode='M',
                                                       clCode='HS',
                                          period='202205',
                                         reporterCode=None, cmdCode='91,90', flowCode='M', partnerCode=None,
                                         partner2Code=None,
                                         customsCode=None, motCode=None)
print("requestID: ",myJson['requestId'])
``` 
- Check status of asynchronous job
``` python
mydf = comtradeapicall.checkAsyncDataRequest(subscription_key, 
                                          batchId ='2f92dd59-9763-474c-b27c-4af9ce16d454' )
``` 
- Submit final data  asynchronous job and download the resulting file
``` python
comtradeapicall.downloadAsyncFinalDataRequest(subscription_key, directory,  typeCode='C', freqCode='M',
                                        clCode='HS', period='202209', reporterCode=None, cmdCode='91,90',
                                        flowCode='M', partnerCode=None, partner2Code=None,
                                        customsCode=None, motCode=None)
``` 
- Submit tariffline data  asynchronous job and download the resulting file
``` python
comtradeapicall.downloadAsyncTarifflineDataRequest(subscription_key, directory,  typeCode='C', freqCode='M',
                                        clCode='HS', period='202209', reporterCode=None, cmdCode='91,90',
                                        flowCode='M', partnerCode=None, partner2Code=None,
                                        customsCode=None, motCode=None)
``` 
- View list of reference tables
``` python
mydf = comtradeapicall.listReference()
mydf = comtradeapicall.listReference('cmd:B5')
``` 
- Download specific reference
``` python
mydf = comtradeapicall.getReference('reporter')
mydf = comtradeapicall.getReference('partner')
``` 
- Convert country/area ISO3 to Comtrade code
``` python
country_code = comtradeapicall.convertCountryIso3ToCode('USA,FRA,CHE,ITA')
``` 
- Get the Standard unit value (qtyUnitCode 8 [kg]) for commodity 010391 in 2022
``` python
mydf = comtradeapicall.getSUV(subscription_key, period='2022', cmdCode='010391', flowCode=None, qtyUnitCode=8)
``` 
- Get data in trade balance layout (exports and imports next to each other)
``` python
mydf = comtradeapicall.getTradeBalance(subscription_key, typeCode='C', freqCode='M', clCode='HS', period='202205',reporterCode='36', cmdCode='TOTAL', partnerCode=None)
``` 
- Get and compare data in bilateral layout (reported data is complemented by mirror partner data)
``` python
mydf = comtradeapicall.getBilateralData(subscription_key, typeCode='C', freqCode='M', clCode='HS', period='202205', reporterCode='36', cmdCode='TOTAL', flowCode='X', partnerCode=None)
``` 
- Get Trade Matrix Data - (estimated) World Export of one digit SITC section in 2024 (note: this may contain estimated trade values)
``` python
mydf = comtradeapicall.getTradeMatrix(subscription_key, typeCode='C', freqCode='A', period='2024', reporterCode='0',cmdCode='ag1', flowCode='X', partnerCode='0', aggregateBy=None, includeDesc=True)
 ``` 
## Script Examples
- Examples folder contains more use cases including calculation of unit value, tracking top traded products
- Tests folder contains examples of using the lib

## Downloaded file name convention
The naming convention follows the following : "COMTRADE-\<DATA>-\<TYPE>\<FREQ>\<COUNTRY CODE>\<YEAR\[
-MONTH\]>\<CLASSIFICATION CODE>\[\<RELEASE DATE\>\]"

As examples:
- Final merchandise trade data from Morocco (code 504) in March 2000 released on 3 Jan 2023 coded using H1
 classification:
  - *COMTRADE-FINAL-CM504200003H1[2023-01-03]*
- Tariffline merchandise trade from Morocco (code 504) in March 2000 released on 3 Jan 2023 coded using H1 classification: 
  - *COMTRADE-TARIFFLINE-CM504200003H1[2023-01-03]*

Note: Async download retains the original batch id










