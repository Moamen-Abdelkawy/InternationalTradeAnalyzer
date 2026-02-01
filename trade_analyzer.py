"""
Trade Data Analysis Script
Supports two data sources:
  - BACI: 1995-2024 annual data (harmonized bilateral flows)
  - COMTRADE API: Flexible periods and monthly data (as reported by countries)
User can choose which data source to use for analysis.
"""

import pandas as pd
import os
import re
import difflib
from pathlib import Path
from dotenv import load_dotenv
import comtradeapicall
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns

# Monkey-patch pandas concat to be future-proof by cleaning dataframes before concatenation
_original_concat = pd.concat

def _future_proof_concat(objs, *args, **kwargs):
    """
    Future-proof wrapper for pandas concat that removes all-NA columns before concatenation.
    This prevents FutureWarning about empty/all-NA entries in concat operations.
    """
    if objs is not None:
        # Clean each dataframe by removing all-NA columns
        cleaned_objs = []
        for obj in objs:
            if isinstance(obj, pd.DataFrame) and not obj.empty:
                # Remove columns that are entirely NA
                cleaned_obj = obj.dropna(axis=1, how='all')
                cleaned_objs.append(cleaned_obj)
            else:
                cleaned_objs.append(obj)

        # Only proceed if we have non-empty dataframes
        if cleaned_objs:
            return _original_concat(cleaned_objs, *args, **kwargs)

    # Fallback to original if no valid objects
    return _original_concat(objs, *args, **kwargs)

# Apply the patch
pd.concat = _future_proof_concat


class TradeAnalyzer:
    """Trade data analyzer supporting BACI (1995-2024) and COMTRADE data sources"""

    def __init__(self):
        self.base_dir = Path(__file__).parent

        # BACI setup
        self.baci_dir = self.base_dir / "data" / "BACI" / "BACI_HS92_V202601"
        self.baci_country_codes = None
        self.baci_product_codes = None

        # COMTRADE setup
        self.subscription_key = self.load_subscription_key()
        self.comtrade_reporter_cache = None
        self.comtrade_partner_cache = None

        # Load reference data
        self.load_baci_reference_data()

        # Store selected data source (will be set during analysis)
        self.selected_source = None

        print("✓ Trade analyzer initialized\n")

    def load_subscription_key(self):
        """Load UN COMTRADE API subscription key"""
        env_path = self.base_dir / "SUBSCRIPTION_KEY.env"
        if not env_path.exists():
            raise FileNotFoundError(
                f"SUBSCRIPTION_KEY.env file not found at {env_path}\n"
                "Please create this file with your PRIMARY_KEY"
            )

        load_dotenv(env_path)
        key = os.getenv("PRIMARY_KEY")
        if not key:
            raise ValueError("PRIMARY_KEY not found in SUBSCRIPTION_KEY.env file")

        return key

    def load_baci_reference_data(self):
        """Load BACI country and product code mappings"""
        try:
            self.baci_country_codes = pd.read_csv(self.baci_dir / "country_codes_V202601.csv")
            self.baci_product_codes = pd.read_csv(self.baci_dir / "product_codes_HS92_V202601.csv")
            print("✓ BACI reference data loaded\n")
        except Exception as e:
            print(f"⚠ Warning: Could not load BACI reference data: {e}")
            print("  BACI data will not be available\n")

    def get_frequency_input(self):
        """Get frequency (Annual or Monthly) from user"""
        while True:
            print("\n" + "="*60)
            print("DATA FREQUENCY")
            print("="*60)
            print("Select the frequency of data for analysis.")
            print("")
            print("VALID INPUTS:")
            print("  A  or  Annual   :  Yearly data")
            print("  M  or  Monthly  :  Monthly data (COMTRADE only)")
            print("")
            freq = input("Enter frequency: ").strip().upper()
            if freq in ['A', 'ANNUAL']:
                return 'A'
            elif freq in ['M', 'MONTHLY']:
                return 'M'
            else:
                print("✗ Invalid input. Please enter A (Annual) or M (Monthly).")

    def get_data_source_input(self, freq_code):
        """Get data source selection from user"""
        # For monthly data, only COMTRADE is available
        if freq_code == 'M':
            print("\n" + "="*60)
            print("DATA SOURCE")
            print("="*60)
            print("Monthly data is only available via COMTRADE API.")
            print("BACI database contains annual data only.")
            print("")
            self.selected_source = 'COMTRADE'
            return 'COMTRADE'

        while True:
            print("\n" + "="*60)
            print("DATA SOURCE")
            print("="*60)
            print("Select the data source for analysis.")
            print("")
            print("VALID INPUTS:")
            print("  B  or  BACI      :  BACI database (1995-2024, harmonized)")
            print("  C  or  COMTRADE  :  UN COMTRADE API (as reported by countries)")
            print("")
            print("NOTE:")
            print("  BACI provides reconciled bilateral trade flows where")
            print("  discrepancies between exporter and importer reports are harmonized.")
            print("  COMTRADE provides data as reported by individual countries.")
            print("")
            source = input("Enter data source: ").strip().upper()
            if source in ['B', 'BACI']:
                self.selected_source = 'BACI'
                return 'BACI'
            elif source in ['C', 'COMTRADE']:
                self.selected_source = 'COMTRADE'
                return 'COMTRADE'
            else:
                print("✗ Invalid input. Please enter B (BACI) or C (COMTRADE).")

    def get_period_input(self, freq_code, data_source):
        """Get and validate period input from user"""
        while True:
            print("\n" + "="*60)
            print("PERIOD SELECTION")
            print("="*60)

            if freq_code == 'A':
                print("Enter the year or range for analysis.")
                print("")
                print("FORMAT:")
                print("  Single year    :  YYYY        (e.g., 2023)")
                print("  Year range     :  YYYY-YYYY   (e.g., 2018-2023)")
                print("")
                if data_source == 'BACI':
                    print("VALID RANGE: 1995-2024 (BACI database)")
                    min_year, max_year = 1995, 2024
                else:
                    import datetime
                    current_year = datetime.datetime.now().year
                    print(f"VALID RANGE: 1962-Present (COMTRADE API)")
                    print("NOTE: Data availability depends on reporting by the selected country.")
                    min_year, max_year = 1962, current_year + 1
                print("")
                period_input = input("Enter year(s): ").strip()

                # Parse period
                if '-' in period_input and not period_input.startswith('-'):
                    try:
                        parts = period_input.split('-')
                        if len(parts) != 2:
                            print("✗ Error: Period format should be 'YYYY-YYYY'")
                            continue

                        start_year = int(parts[0].strip())
                        end_year = int(parts[1].strip())

                        if start_year > end_year:
                            print("✗ Error: Start year must be less than or equal to end year.")
                            continue

                        if not (min_year <= start_year <= max_year and min_year <= end_year <= max_year):
                            print(f"✗ Error: Years must be between {min_year} and {max_year}.")
                            continue

                        years = [str(y) for y in range(start_year, end_year + 1)]
                        period_string = ','.join(years)
                        print(f"✓ Period: {start_year}-{end_year} ({len(years)} years)")
                        return period_string

                    except ValueError:
                        print("✗ Error: Please enter valid years")
                else:
                    try:
                        year = int(period_input.strip())
                        if not (min_year <= year <= max_year):
                            print(f"✗ Error: Year must be between {min_year} and {max_year}.")
                            continue
                        return period_input
                    except ValueError:
                        print("✗ Error: Please enter a valid year.")

            else:  # Monthly - COMTRADE only
                print("Enter the month or range for analysis.")
                print("")
                print("FORMAT:")
                print("  Single month   :  YYYYMM         (e.g., 202312 for December 2023)")
                print("  Month range    :  YYYYMM-YYYYMM  (e.g., 202301-202312)")
                print("")
                print("DATA SOURCE: COMTRADE API (monthly data)")
                print("")
                period_input = input("Enter period(s): ").strip()

                if '-' in period_input and len(period_input.split('-')[0].strip()) == 6:
                    try:
                        parts = period_input.split('-')
                        start_period = parts[0].strip()
                        end_period = parts[1].strip()

                        if len(start_period) != 6 or len(end_period) != 6:
                            print("✗ Error: Period must be 6 digits (YYYYMM)")
                            continue

                        start_year = int(start_period[:4])
                        start_month = int(start_period[4:6])
                        end_year = int(end_period[:4])
                        end_month = int(end_period[4:6])

                        if not (1 <= start_month <= 12 and 1 <= end_month <= 12):
                            print("✗ Error: Month must be between 01 and 12")
                            continue

                        periods = []
                        current_year = start_year
                        current_month = start_month

                        while (current_year < end_year) or (current_year == end_year and current_month <= end_month):
                            periods.append(f"{current_year}{current_month:02d}")
                            current_month += 1
                            if current_month > 12:
                                current_month = 1
                                current_year += 1

                        period_string = ','.join(periods)
                        print(f"✓ Period: {start_period}-{end_period} ({len(periods)} months)")
                        return period_string

                    except ValueError:
                        print("✗ Error: Please enter valid periods")
                else:
                    try:
                        period = period_input.strip()
                        if len(period) != 6:
                            print("✗ Error: Monthly period must be 6 digits (YYYYMM)")
                            continue
                        year = int(period[:4])
                        month = int(period[4:6])
                        if not (1 <= month <= 12):
                            print("✗ Error: Month must be between 01 and 12")
                            continue
                        return period_input
                    except ValueError:
                        print("✗ Error: Please enter valid period in YYYYMM format")

    def get_country_input(self, role="reporter"):
        """Get and validate country input - checks both BACI and COMTRADE"""
        # Load COMTRADE cache if needed
        if self.comtrade_reporter_cache is None:
            print(f"\nLoading COMTRADE {role} reference data...")
            self.comtrade_reporter_cache = comtradeapicall.getReference('reporter')
            self.comtrade_partner_cache = comtradeapicall.getReference('partner')

        comtrade_cache = self.comtrade_reporter_cache if role == "reporter" else self.comtrade_partner_cache

        while True:
            print("\n" + "="*60)
            print(f"{role.upper()} COUNTRY SELECTION")
            print("="*60)
            print(f"Enter the {role} country by name or numeric code.")
            print("")
            print("VALID INPUTS:")
            print("  Country name     :  e.g., Egypt, United States, China")
            print("  Country code     :  e.g., 818 (Egypt), 842 (USA), 156 (China)")
            if role == "partner":
                print("")
                print("  0  or  World     :  All trading partners (world total)")
            print("")
            print("REFERENCE: Country codes can be found in data/meta/country_codes_V202601.csv")
            print("")
            country_input = input(f"Enter {role} country: ").strip()

            # Check for World/All (partner only)
            if role == "partner" and country_input.lower() in ['0', 'world', 'all']:
                print(f"✓ Selected: All {role}s (World)")
                return '0', 'World', 0

            # Try numeric code first
            try:
                country_code = int(country_input)

                # Check COMTRADE
                comtrade_match = comtrade_cache[comtrade_cache['id'] == country_code]
                comtrade_name = comtrade_match.iloc[0]['text'] if not comtrade_match.empty else None

                # Check BACI
                baci_match = self.baci_country_codes[self.baci_country_codes['country_code'] == country_code]
                baci_name = baci_match.iloc[0]['country_name'] if not baci_match.empty else None

                if comtrade_name or baci_name:
                    # Show both if different
                    if comtrade_name and baci_name:
                        if comtrade_name.lower() == baci_name.lower():
                            print(f"✓ Country found: {comtrade_name} (Code: {country_code})")
                            print(f"  Available in both BACI and COMTRADE")
                        else:
                            print(f"✓ Country found (Code: {country_code}):")
                            print(f"  COMTRADE: {comtrade_name}")
                            print(f"  BACI: {baci_name}")
                    elif comtrade_name:
                        print(f"✓ Country found: {comtrade_name} (Code: {country_code})")
                        print(f"  Available in COMTRADE only")
                    else:
                        print(f"✓ Country found: {baci_name} (Code: {country_code})")
                        print(f"  Available in BACI only")

                    confirm = input("Confirm selection (Y/N): ").strip().upper()
                    if confirm in ['Y', 'YES']:
                        final_name = comtrade_name or baci_name
                        baci_code = baci_match.iloc[0]['country_code'] if not baci_match.empty else None
                        return str(country_code), final_name, baci_code
                else:
                    print(f"✗ Country code {country_code} not found in either database.")

            except ValueError:
                # Search by text
                comtrade_matches = comtrade_cache[
                    comtrade_cache['text'].str.contains(country_input, case=False, na=False)
                ]

                baci_matches = self.baci_country_codes[
                    self.baci_country_codes['country_name'].str.contains(country_input, case=False, na=False)
                ]

                if len(comtrade_matches) == 1 and len(baci_matches) <= 1:
                    comtrade_code = str(comtrade_matches.iloc[0]['id'])
                    comtrade_name = comtrade_matches.iloc[0]['text']
                    baci_code = baci_matches.iloc[0]['country_code'] if not baci_matches.empty else None
                    baci_name = baci_matches.iloc[0]['country_name'] if not baci_matches.empty else None

                    if baci_name and comtrade_name.lower() != baci_name.lower():
                        print(f"✓ Country found:")
                        print(f"  COMTRADE: {comtrade_name} (Code: {comtrade_code})")
                        print(f"  BACI: {baci_name} (Code: {baci_code})")
                    else:
                        print(f"✓ Country found: {comtrade_name} (Code: {comtrade_code})")

                    confirm = input("Confirm selection (Y/N): ").strip().upper()
                    if confirm in ['Y', 'YES']:
                        return comtrade_code, comtrade_name, baci_code

                elif len(comtrade_matches) == 0 and len(baci_matches) == 0:
                    print(f"✗ Error: No country found matching '{country_input}'")

                    # Try fuzzy matching to suggest similar country names
                    all_country_names = list(comtrade_cache['text'].dropna().unique())
                    if self.baci_country_codes is not None:
                        all_country_names.extend(list(self.baci_country_codes['country_name'].dropna().unique()))
                    all_country_names = list(set(all_country_names))  # Remove duplicates

                    similar = difflib.get_close_matches(country_input, all_country_names, n=5, cutoff=0.6)
                    if similar:
                        print(f"\nDid you mean one of these?")
                        for suggestion in similar:
                            print(f"  - {suggestion}")
                        print("")
                else:
                    print(f"Multiple countries found matching '{country_input}':")
                    # Combine matches from both sources, filtering out empty dataframes
                    matches_list = []
                    if len(comtrade_matches) > 0:
                        matches_list.append(comtrade_matches[['id', 'text']].rename(columns={'id': 'code', 'text': 'name'}))
                    if len(baci_matches) > 0:
                        matches_list.append(baci_matches[['country_code', 'country_name']].rename(columns={'country_code': 'code', 'country_name': 'name'}))

                    if len(matches_list) == 1:
                        all_matches = matches_list[0].drop_duplicates()
                    else:
                        all_matches = pd.concat(matches_list).drop_duplicates()

                    for idx, row in all_matches.head(10).iterrows():
                        print(f"  {row['code']}: {row['name']}")
                    print("\nPlease enter a more specific name or use the country code.")

    def get_product_input(self):
        """Get and validate product code input with subcategory details"""
        while True:
            print("\n" + "="*60)
            print("PRODUCT SELECTION")
            print("="*60)
            print("Enter the HS (Harmonized System) product code.")
            print("")
            print("VALID INPUTS:")
            print("  2-digit chapter     :  e.g., 10 (Cereals)")
            print("  4-digit heading     :  e.g., 1001 (Wheat)")
            print("  6-digit subheading  :  e.g., 100190 (Wheat, other)")
            print("")
            print("SPECIAL CODES:")
            print("  TOTAL  :  All products combined")
            print("  AG2    :  All 2-digit chapters")
            print("  AG4    :  All 4-digit headings")
            print("  AG6    :  All 6-digit subheadings")
            print("")
            print("REFERENCE: Product codes can be found in data/meta/product_codes_HS92_V202601.csv")
            print("")
            product_input = input("Enter product code: ").strip().upper()

            if not product_input:
                print("✗ Error: Product code cannot be empty")
                continue

            # Handle special codes
            if product_input in ['TOTAL', 'AG2', 'AG4', 'AG6']:
                return product_input, f"{product_input} - All products at specified level"

            # Check BACI for exact match and subcategories
            baci_desc = None
            subcategories = None

            if self.baci_product_codes is not None:
                try:
                    # Normalize product code for comparison
                    # Reference file has 6-digit codes with leading zeros (e.g., "010210")
                    # User might enter with or without leading zeros
                    product_input_clean = product_input.lstrip('0') or '0'  # Remove leading zeros for comparison

                    # Create normalized code column for matching (strip leading zeros from reference)
                    ref_codes = self.baci_product_codes.copy()
                    ref_codes['code_normalized'] = ref_codes['code'].astype(str).str.lstrip('0')
                    ref_codes['code_normalized'] = ref_codes['code_normalized'].replace('', '0')

                    # Check for exact match
                    exact_match = ref_codes[ref_codes['code_normalized'] == product_input_clean]

                    if not exact_match.empty:
                        baci_desc = exact_match.iloc[0]['description']

                    # Check for subcategories (codes that start with input pattern)
                    # Use the original code column for prefix matching
                    input_len = len(product_input_clean)
                    subcategories = ref_codes[
                        (ref_codes['code_normalized'].str[:input_len] == product_input_clean) &
                        (ref_codes['code_normalized'].str.len() > input_len)
                    ]

                    if not subcategories.empty:
                        # Found subcategories
                        print(f"\n⚠ Product code '{product_input}' has {len(subcategories)} subcategories:")
                        print("="*60)
                        for idx, row in subcategories.head(20).iterrows():
                            desc_short = row['description'][:60] if len(row['description']) > 60 else row['description']
                            print(f"  {row['code']}: {desc_short}")
                        if len(subcategories) > 20:
                            print(f"  ... and {len(subcategories) - 20} more")
                        print("="*60)

                        if baci_desc:
                            print(f"\nBroad category: {product_input} - {baci_desc}")

                        print("\nData will automatically aggregate all subcategories.")
                        print("Use this code to get all subcategories combined?")
                        confirm = input("Confirm selection (Y/N): ").strip().upper()

                        if confirm in ['Y', 'YES']:
                            main_desc = f"{product_input} - {baci_desc if baci_desc else 'All subcategories'} ({len(subcategories)} subcategories)"
                            print(f"\n✓ Using code {product_input} ({len(subcategories)} subcategories will be aggregated)")
                            return product_input, main_desc
                        else:
                            print("Please enter a different code.")
                            continue

                    elif baci_desc:
                        # Exact match, no subcategories
                        print(f"✓ Product: {product_input} - {baci_desc}")
                        confirm = input("Confirm selection (Y/N): ").strip().upper()
                        if confirm in ['Y', 'YES']:
                            return product_input, baci_desc
                    else:
                        # No match in BACI reference, but code can still be used
                        print(f"✓ Using product code: {product_input}")
                        print("  (Code not found in BACI reference data)")
                        confirm = input("Confirm selection (Y/N): ").strip().upper()
                        if confirm in ['Y', 'YES']:
                            return product_input, f"Product code: {product_input}"

                except ValueError:
                    print("✗ Please enter a valid numeric product code.")
            else:
                # BACI reference not available, proceed with code
                print(f"✓ Using product code: {product_input}")
                confirm = input("Confirm selection (Y/N): ").strip().upper()
                if confirm in ['Y', 'YES']:
                    return product_input, f"Product code: {product_input}"

    def get_trade_direction(self):
        """Get trade direction from user"""
        while True:
            print("\n" + "="*60)
            print("TRADE DIRECTION")
            print("="*60)
            print("Select the trade flow direction for analysis.")
            print("")
            print("VALID INPUTS:")
            print("  M  or  Imports  :  Goods imported by the reporter country")
            print("  X  or  Exports  :  Goods exported by the reporter country")
            print("")
            direction = input("Enter trade direction: ").strip().upper()
            if direction in ['M', 'IMPORTS', 'IMPORT']:
                return 'M', 'Imports'
            elif direction in ['X', 'EXPORTS', 'EXPORT']:
                return 'X', 'Exports'
            else:
                print("✗ Invalid input. Please enter M (Imports) or X (Exports).")

    def get_partner_choice(self):
        """Get partner analysis choice from user"""
        while True:
            print("\n" + "="*60)
            print("PARTNER SELECTION")
            print("="*60)
            print("Select the type of partner analysis.")
            print("")
            print("VALID INPUTS:")
            print("  A  or  All       :  Analyze trade with all partners (world total)")
            print("  S  or  Specific  :  Analyze trade with a specific partner country")
            print("")
            choice = input("Enter choice: ").strip().upper()
            if choice in ['A', 'ALL']:
                return 'all', None, None, None
            elif choice in ['S', 'SPECIFIC']:
                partner_code, partner_name, baci_code = self.get_country_input("partner")
                return 'specific', partner_code, partner_name, baci_code
            else:
                print("✗ Invalid input. Please enter A (All) or S (Specific).")

    def get_metric_choice_baci(self):
        """Get metric choice for BACI data (only Value and Quantity available)"""
        while True:
            print("\n" + "="*60)
            print("METRIC SELECTION (BACI)")
            print("="*60)
            print("Select the metric to rank trading partners.")
            print("")
            print("VALID INPUTS:")
            print("  V  or  Value     :  Trade Value in USD")
            print("  Q  or  Quantity  :  Quantity in Metric Tons")
            print("")
            print("NOTE: The selected metric will be used to rank partners.")
            print("      All available metrics will be included in the CSV output.")
            print("")
            print("WARNING: Quantity data may be less reliable than Value data.")
            print("         Reporting practices vary by country and product.")
            print("")
            choice = input("Enter metric: ").strip().upper()
            if choice in ['V', 'VALUE']:
                return 'Trade_Value_USD', 'value', 'v'
            elif choice in ['Q', 'QUANTITY']:
                return 'Quantity_MT', 'quantity', 'q'
            else:
                print("✗ Invalid input. Please enter V (Value) or Q (Quantity).")

    def get_metric_choice_comtrade(self, available_metrics):
        """Get metric choice for COMTRADE data based on actual available metrics"""
        while True:
            print("\n" + "="*60)
            print("METRIC SELECTION (COMTRADE)")
            print("="*60)
            print("Select the metric to rank trading partners.")
            print("")
            print("AVAILABLE METRICS FROM API RESPONSE:")

            # Build list of available metrics with their codes and shortcuts
            metric_options = []
            shortcut_map = {}
            option_num = 1

            # Define metric info: (api_column, display_name, metric_type, shortcut)
            metric_defs = [
                ('primaryValue', 'Primary_Value_USD', 'value', 'PV'),
                ('fobValue', 'FOB_Value_USD', 'value', 'FOB'),
                ('cifValue', 'CIF_Value_USD', 'value', 'CIF'),
                ('qty', 'Quantity', 'quantity', 'QTY'),
                ('netWgt', 'Net_Weight_Kg', 'weight', 'NW'),
                ('grossWgt', 'Gross_Weight_Kg', 'weight', 'GW'),
            ]

            for api_col, display_name, mtype, shortcut in metric_defs:
                if api_col in available_metrics and available_metrics[api_col] > 0:
                    unit = "USD" if mtype == 'value' else ("Kg" if mtype == 'weight' else "units")
                    print(f"  {option_num}  or  {shortcut:4s}:  {display_name.replace('_', ' ')} ({available_metrics[api_col]:,} records)")
                    metric_options.append((api_col, display_name, mtype, shortcut))
                    # Map both number and shortcut to this option
                    shortcut_map[str(option_num)] = (api_col, display_name, mtype)
                    shortcut_map[shortcut] = (api_col, display_name, mtype)
                    option_num += 1

            if not metric_options:
                print("  ⚠ No metrics available in API response!")
                return None, None, None

            print("")
            print("NOTE: The selected metric will be used to rank partners.")
            print("      All available metrics will be included in the CSV output.")
            print("")
            print("WARNING: Metrics other than Value (USD) may be less reliable.")
            print("         Reporting practices vary by country and product.")
            print("")
            choice = input("Enter metric: ").strip().upper()

            # Find selected metric
            if choice in shortcut_map:
                api_col, display_name, mtype = shortcut_map[choice]
                return display_name, mtype, api_col
            else:
                print("✗ Invalid input. Please enter a valid metric number or code.")

    def sanitize_filename(self, text, max_length=50):
        """Sanitize text for use in filename"""
        sanitized = re.sub(r'[^\w\s-]', '', text)
        sanitized = re.sub(r'[\s]+', '_', sanitized)
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length].rstrip('_')
        return sanitized

    def get_product_code_for_filename(self, product_desc):
        """Extract product code from product description for use in filenames"""
        # Examples of inputs:
        # "10 - Cereals (227 subcategories)"
        # "1001 - Wheat"
        # "Product code: 10"
        # "TOTAL - All products at specified level"
        # "AG2 - All products at specified level"

        # Handle special codes
        if product_desc.startswith(('TOTAL', 'AG2', 'AG4', 'AG6')):
            return product_desc.split(' - ')[0].strip()

        # Extract code before " - "
        if ' - ' in product_desc:
            code = product_desc.split(' - ')[0].strip()
            # Verify it's a valid code (numeric or special)
            if code.isdigit() or code in ['TOTAL', 'AG2', 'AG4', 'AG6']:
                return f"HS{code}"

        # Try to extract from "Product code: X" format
        match = re.search(r'Product code:\s*(\w+)', product_desc)
        if match:
            return f"HS{match.group(1)}"

        # Fallback: return first 10 chars sanitized
        return self.sanitize_filename(product_desc, max_length=10)

    def get_clean_product_desc(self, product_desc):
        """Extract clean product description without code and subcategory info"""
        # Examples of inputs:
        # "10 - Cereals (227 subcategories)"
        # "10 - All subcategories (16 subcategories)"
        # "1001 - Wheat"
        # "Product code: 10"

        # Remove subcategory info in parentheses
        desc = re.sub(r'\s*\(\d+\s+subcategor(y|ies)\)', '', product_desc)

        # Extract description after dash if present
        if ' - ' in desc:
            parts = desc.split(' - ', 1)
            code = parts[0].strip()
            description = parts[1].strip() if len(parts) > 1 else ''

            # If description is generic, try to look up the actual product name
            if description in ['All subcategories', ''] or description.startswith('Product code'):
                # Try to get description from BACI product codes
                if hasattr(self, 'baci_product_codes') and self.baci_product_codes is not None:
                    try:
                        # Reference file stores codes as strings with leading zeros (e.g., "010210")
                        # Pad the code to 6 digits for proper matching
                        code_padded = str(code).zfill(6)
                        match = self.baci_product_codes[self.baci_product_codes['code'].astype(str).str.zfill(6) == code_padded]
                        if not match.empty:
                            return match.iloc[0]['description']
                    except:
                        pass

                # If lookup fails, use descriptive text
                return f"Products with code starting with {code}"

            return description

        # Remove "Product code:" prefix if present
        desc = re.sub(r'Product code:\s*', '', desc)

        return desc.strip()

    def load_baci_data(self, years, reporter_baci_code, product_code, flow_code, keep_subcategories=False):
        """Load BACI data for specified years using chunked reading with filtering"""
        if not years or reporter_baci_code is None:
            return None

        print(f"\nLoading BACI data for {len(years)} year(s)...")
        all_data = []

        # Prepare product filter
        # BACI stores product codes as integers (e.g., 10210 for HS code 010210)
        # User may enter with or without leading zeros
        # Normalize by removing leading zeros for consistent comparison
        product_code_clean = str(product_code).lstrip('0') or '0'
        try:
            product_int = int(product_code_clean)
        except:
            product_int = None

        # Determine which column to filter for country based on direction
        # BACI columns: t (year), i (exporter), j (importer), k (product), v (value), q (quantity)
        if flow_code == 'M':  # Imports - reporter is importer (j)
            country_col = 'j'
            partner_col = 'i'
        else:  # Exports - reporter is exporter (i)
            country_col = 'i'
            partner_col = 'j'

        for year in years:
            filename = f"BACI_HS92_Y{year}_V202601.csv"
            filepath = self.baci_dir / filename

            if not filepath.exists():
                print(f"  ⚠ Warning: {filename} not found, skipping year {year}")
                continue

            print(f"  Loading {year}...", end=" ", flush=True)
            try:
                # Use chunked reading with filtering to avoid loading entire file into memory
                chunk_size = 500000
                year_data = []
                records_loaded = 0

                for chunk in pd.read_csv(filepath, chunksize=chunk_size):
                    # Filter by country first (most restrictive)
                    chunk_filtered = chunk[chunk[country_col] == reporter_baci_code]

                    if len(chunk_filtered) == 0:
                        continue

                    # Filter by product (exact match or prefix match for subcategories)
                    # BACI 'k' column is integer, so compare accordingly
                    if product_int is not None:
                        # For prefix matching: convert k to string (no leading zeros) and check prefix
                        k_str = chunk_filtered['k'].astype(str)
                        chunk_filtered = chunk_filtered[
                            (chunk_filtered['k'] == product_int) |
                            (k_str.str.startswith(product_code_clean))
                        ]
                    else:
                        chunk_filtered = chunk_filtered[chunk_filtered['k'].astype(str) == product_code_clean]

                    if len(chunk_filtered) > 0:
                        year_data.append(chunk_filtered)
                        records_loaded += len(chunk_filtered)

                if year_data:
                    combined_year = pd.concat(year_data, ignore_index=True)
                    all_data.append(combined_year)
                    print(f"✓ {records_loaded:,} records")
                else:
                    print(f"✓ 0 records (no matching data)")

            except Exception as e:
                print(f"✗ Error loading {year}: {e}")
                continue

        if not all_data:
            print("  ✗ No BACI data loaded")
            return None

        # Combine all years
        filtered = pd.concat(all_data, ignore_index=True)
        print(f"  ✓ Total: {len(filtered):,} relevant records")

        # Aggregate - with or without subcategories
        if keep_subcategories:
            # Keep product code for subcategory analysis
            aggregated = filtered.groupby([partner_col, 'k', 't']).agg({
                'v': 'sum',  # value in thousand USD
                'q': 'sum'   # quantity in metric tons
            }).reset_index()

            aggregated.columns = ['partner_code', 'product_code', 'year', 'value_thousand_usd', 'quantity_mt']

            # Convert BACI value from thousand USD to USD
            aggregated['value_usd'] = aggregated['value_thousand_usd'] * 1000

            # Map partner codes to names
            # Ensure data types match for merge - convert to int
            country_codes_for_merge = self.baci_country_codes[['country_code', 'country_name']].copy()
            country_codes_for_merge['country_code'] = pd.to_numeric(country_codes_for_merge['country_code'], errors='coerce').astype('Int64')

            aggregated = aggregated.merge(
                country_codes_for_merge,
                left_on='partner_code',
                right_on='country_code',
                how='left'
            )

            # Map product codes to descriptions
            # BACI data has integer codes (e.g., 10210), reference file has string codes with leading zeros (e.g., "010210")
            # Normalize both by padding integers to 6 digits for proper matching
            aggregated['product_code_padded'] = aggregated['product_code'].astype(str).str.zfill(6)
            product_codes_for_merge = self.baci_product_codes[['code', 'description']].copy()
            product_codes_for_merge['code'] = product_codes_for_merge['code'].astype(str).str.zfill(6)

            aggregated = aggregated.merge(
                product_codes_for_merge,
                left_on='product_code_padded',
                right_on='code',
                how='left'
            )
            aggregated.drop(columns=['product_code_padded'], inplace=True)

            # Clean up
            aggregated = aggregated[['partner_code', 'country_name', 'product_code', 'description', 'year', 'value_usd', 'quantity_mt']]
            aggregated.columns = ['Partner_Code', 'Partner_Name', 'Product_Code', 'Product_Desc', 'Year', 'Trade_Value_USD', 'Quantity_MT']

            # Fill missing names
            aggregated['Partner_Name'] = aggregated['Partner_Name'].fillna('Unknown')
            aggregated['Product_Desc'] = aggregated['Product_Desc'].fillna('Unknown Product')

        else:
            # Aggregate by partner and year only (no subcategories)
            aggregated = filtered.groupby([partner_col, 't']).agg({
                'v': 'sum',  # value in thousand USD
                'q': 'sum'   # quantity in metric tons
            }).reset_index()

            aggregated.columns = ['partner_code', 'year', 'value_thousand_usd', 'quantity_mt']

            # Convert BACI value from thousand USD to USD
            aggregated['value_usd'] = aggregated['value_thousand_usd'] * 1000

            # Map partner codes to names
            # Ensure data types match for merge - convert to int
            country_codes_for_merge = self.baci_country_codes[['country_code', 'country_name']].copy()
            country_codes_for_merge['country_code'] = pd.to_numeric(country_codes_for_merge['country_code'], errors='coerce').astype('Int64')

            aggregated = aggregated.merge(
                country_codes_for_merge,
                left_on='partner_code',
                right_on='country_code',
                how='left'
            )

            # Clean up
            aggregated = aggregated[['partner_code', 'country_name', 'year', 'value_usd', 'quantity_mt']]
            aggregated.columns = ['Partner_Code', 'Partner_Name', 'Year', 'Trade_Value_USD', 'Quantity_MT']

            # Fill missing partner names
            aggregated['Partner_Name'] = aggregated['Partner_Name'].fillna('Unknown')

        print(f"  ✓ BACI data ready: {len(aggregated)} records")
        return aggregated

    def fetch_comtrade_data(self, freq_code, period, reporter_code, cmd_code, flow_code, partner_code=None):
        """Fetch data from COMTRADE API"""
        print(f"\nFetching COMTRADE data...")
        print(f"  Parameters: freq={freq_code}, period={period}, reporter={reporter_code}")
        print(f"  Product={cmd_code}, flow={flow_code}, partner={partner_code or 'all'}")

        try:
            data = comtradeapicall._getFinalData(
                subscription_key=self.subscription_key,
                typeCode='C',
                freqCode=freq_code,
                clCode='HS',  # Using HS classification to match BACI
                period=period,
                reporterCode=reporter_code,
                cmdCode=cmd_code,
                flowCode=flow_code,
                partnerCode=partner_code,
                partner2Code=None,
                customsCode=None,
                motCode=None,
                maxRecords=250000,
                format_output='JSON',
                aggregateBy=None,
                breakdownMode='classic',
                countOnly=False,
                includeDesc=True
            )

            if data is None or len(data) == 0:
                print("  ✗ No data returned from COMTRADE API")
                print("")
                print("  Possible reasons:")
                print("    - The country may not have reported data for this period yet")
                print("    - The product code may not have trade for this country/period")
                print("    - Data for recent periods (e.g., 2025) may not be fully available")
                print("")
                print("  Try checking data availability at: https://comtradeplus.un.org/")
                return None

            # Filter out World (code 0) if partner_code is None
            if partner_code is None:
                data = data[data['partnerCode'] != 0]

            print(f"  ✓ Fetched {len(data):,} records from COMTRADE (before filtering)")

            # Store original data for fallback
            original_data = data.copy()

            # CRITICAL: Try to get ONLY leaf-level (subcategory) records first
            if 'isLeaf' in data.columns:
                before_count = len(data)
                leaf_data = data[data['isLeaf'] == True].copy()
                removed = before_count - len(leaf_data)

                if len(leaf_data) > 0:
                    # Success: We have subcategory data
                    print(f"  ✓ Using {len(leaf_data):,} leaf-level (subcategory) records")
                    if removed > 0:
                        print(f"  ✓ Filtered out {removed} aggregate record(s)")
                    data = leaf_data
                    # Mark as subcategory data
                    data['Data_Level'] = 'Subcategory'
                else:
                    # Fallback: No leaf data available, use aggregates
                    print(f"  ⚠ WARNING: No leaf-level subcategory data available")
                    print(f"  ⚠ USING {len(original_data)} AGGREGATE RECORD(S) as fallback")
                    print(f"  ⚠ Results will show AGGREGATE-LEVEL data (not broken down by subcategories)")
                    data = original_data
                    # Mark as aggregate data
                    data['Data_Level'] = 'Aggregate'
            else:
                # No isLeaf column, assume all data is valid
                data['Data_Level'] = 'Unknown'

            print(f"  ✓ Final COMTRADE data: {len(data):,} record(s)")
            return data

        except Exception as e:
            print(f"  ✗ Error fetching COMTRADE data: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_comtrade_available_metrics(self, data):
        """Extract available metrics from COMTRADE data"""
        if data is None or len(data) == 0:
            return {}

        available = {}
        metric_cols = ['primaryValue', 'fobValue', 'cifValue', 'qty', 'netWgt', 'grossWgt']

        for col in metric_cols:
            if col in data.columns:
                non_null = data[col].notna().sum()
                if non_null > 0:
                    available[col] = non_null

        return available

    def process_comtrade_data(self, data, freq_code, selected_metric_col, keep_subcategories=False):
        """Process and aggregate COMTRADE data using the selected metric"""
        if data is None or len(data) == 0:
            return None

        print("\nProcessing COMTRADE data...")
        print(f"  Processing {len(data)} record(s)...")
        print(f"  Selected metric column: {selected_metric_col}")

        # Determine grouping columns
        period_col = 'refPeriodId' if 'refPeriodId' in data.columns else 'period'

        if keep_subcategories:
            group_cols = ['partnerCode', 'partnerDesc', 'cmdCode', 'cmdDesc', period_col]
        else:
            group_cols = ['partnerCode', 'partnerDesc', period_col]

        # For annual data, extract year
        if freq_code == 'A':
            data['year_only'] = data[period_col].astype(str).str[:4].astype(int)
            if keep_subcategories:
                group_cols = ['partnerCode', 'partnerDesc', 'cmdCode', 'cmdDesc', 'year_only']
            else:
                group_cols = ['partnerCode', 'partnerDesc', 'year_only']
            time_col_name = 'Year'
        else:
            time_col_name = 'Period'

        # Aggregate ALL available metric columns (not just the selected one)
        # The selected metric is used for ranking, but all metrics go into CSV
        all_metric_cols = ['primaryValue', 'fobValue', 'cifValue', 'qty', 'netWgt', 'grossWgt']
        agg_dict = {}
        for col in all_metric_cols:
            if col in data.columns:
                agg_dict[col] = 'sum'

        # Store the selected metric column name for later use
        self._comtrade_selected_metric = selected_metric_col

        # Preserve Data_Level marker if it exists
        data_level = None
        if 'Data_Level' in data.columns:
            data_level = data['Data_Level'].iloc[0] if len(data) > 0 else 'Unknown'

        aggregated = data.groupby(group_cols).agg(agg_dict).reset_index()

        if data_level:
            aggregated['Data_Level'] = data_level

        # Rename grouping columns based on structure
        # Keep metric columns with their original names for clarity
        rename_map = {}
        if keep_subcategories:
            rename_map = {
                'partnerCode': 'Partner_Code',
                'partnerDesc': 'Partner_Name',
                'cmdCode': 'Product_Code',
                'cmdDesc': 'Product_Desc',
                'year_only': 'Year' if freq_code == 'A' else None,
                period_col: 'Period' if freq_code != 'A' else None
            }
        else:
            rename_map = {
                'partnerCode': 'Partner_Code',
                'partnerDesc': 'Partner_Name',
                'year_only': 'Year' if freq_code == 'A' else None,
                period_col: 'Period' if freq_code != 'A' else None
            }

        # Remove None values from rename_map
        rename_map = {k: v for k, v in rename_map.items() if v is not None}
        aggregated = aggregated.rename(columns=rename_map)

        # Rename metric columns to user-friendly names
        metric_rename = {
            'primaryValue': 'Primary_Value_USD',
            'fobValue': 'FOB_Value_USD',
            'cifValue': 'CIF_Value_USD',
            'qty': 'Quantity',
            'netWgt': 'Net_Weight_Kg',
            'grossWgt': 'Gross_Weight_Kg'
        }
        aggregated = aggregated.rename(columns=metric_rename)

        # Add Metric_Value column as a copy of the selected metric for backwards compatibility
        selected_friendly_name = metric_rename.get(selected_metric_col, selected_metric_col)
        if selected_friendly_name in aggregated.columns:
            aggregated['Metric_Value'] = aggregated[selected_friendly_name]

        if keep_subcategories:
            # Try to fill missing product descriptions from BACI database
            if hasattr(self, 'baci_product_codes') and self.baci_product_codes is not None:
                baci_codes = self.baci_product_codes.copy()
                baci_codes['code_padded'] = baci_codes['code'].astype(str).str.zfill(6)

                for idx, row in aggregated[aggregated['Product_Desc'].isna()].iterrows():
                    code_padded = str(row['Product_Code']).zfill(6)
                    match = baci_codes[baci_codes['code_padded'] == code_padded]
                    if not match.empty:
                        aggregated.at[idx, 'Product_Desc'] = match.iloc[0]['description']

            aggregated['Product_Desc'] = aggregated['Product_Desc'].fillna('Unknown Product')

        print(f"  ✓ Processed {len(aggregated)} COMTRADE record(s)")
        return aggregated

    def merge_data_sources(self, baci_data, comtrade_data, freq_code):
        """Merge BACI and COMTRADE data intelligently"""
        print("\nMerging data sources...")

        if baci_data is None and comtrade_data is None:
            print("  ✗ No data from either source")
            return None

        if baci_data is None:
            print("  ✓ Using COMTRADE data only")
            # Check if COMTRADE data is aggregate
            if 'Data_Level' in comtrade_data.columns and comtrade_data['Data_Level'].iloc[0] == 'Aggregate':
                print("  ⚠ WARNING: COMTRADE data is at AGGREGATE LEVEL (no subcategory breakdown)")
            return comtrade_data

        if comtrade_data is None:
            print("  ✓ Using BACI data only")
            return baci_data

        # Both sources available - merge
        # BACI is primary for 2002-2023, COMTRADE for 2024+

        # Standardize column names for merging
        period_col = 'Year' if freq_code == 'A' else 'Period'

        # Check if this is subcategory data (has Product_Code column)
        has_subcategories = 'Product_Code' in baci_data.columns or 'Product_Code' in comtrade_data.columns

        if has_subcategories:
            # Merging subcategory data
            common_cols = ['Partner_Code', 'Partner_Name', 'Product_Code', 'Product_Desc', period_col, 'Trade_Value_USD', 'Quantity_MT']

            baci_final = baci_data[common_cols].copy() if 'Product_Code' in baci_data.columns else pd.DataFrame(columns=common_cols)
            baci_final['Source'] = 'BACI'

            # COMTRADE processing
            if 'Product_Code' in comtrade_data.columns:
                comtrade_final = comtrade_data.copy()

                # Ensure Quantity_MT exists in COMTRADE
                if 'Quantity_MT' not in comtrade_final.columns:
                    if 'Net_Weight_MT' in comtrade_final.columns:
                        comtrade_final['Quantity_MT'] = comtrade_final['Net_Weight_MT']
                    else:
                        comtrade_final['Quantity_MT'] = 0

                comtrade_final['Source'] = 'COMTRADE'
                comtrade_final = comtrade_final[common_cols + ['Source']].copy()
            else:
                comtrade_final = pd.DataFrame(columns=common_cols + ['Source'])

        else:
            # Merging partner-level data (no subcategories)
            baci_final = baci_data[['Partner_Code', 'Partner_Name', period_col, 'Trade_Value_USD', 'Quantity_MT']].copy()
            baci_final['Source'] = 'BACI'

            # COMTRADE may have different quantity column name
            comtrade_final = comtrade_data.copy()
            comtrade_final['Source'] = 'COMTRADE'

            # Ensure Quantity_MT exists in COMTRADE
            if 'Quantity_MT' not in comtrade_final.columns:
                if 'Net_Weight_MT' in comtrade_final.columns:
                    comtrade_final['Quantity_MT'] = comtrade_final['Net_Weight_MT']
                else:
                    comtrade_final['Quantity_MT'] = 0

            # Select matching columns
            comtrade_final = comtrade_final[['Partner_Code', 'Partner_Name', period_col, 'Trade_Value_USD', 'Quantity_MT', 'Source']].copy()

        # Combine datasets - filter out empty dataframes to avoid FutureWarning
        dataframes_to_merge = []
        if len(baci_final) > 0:
            dataframes_to_merge.append(baci_final)
        if len(comtrade_final) > 0:
            dataframes_to_merge.append(comtrade_final)

        if len(dataframes_to_merge) == 0:
            print("  ✗ No data available after filtering")
            return None
        elif len(dataframes_to_merge) == 1:
            combined = dataframes_to_merge[0]
        else:
            combined = pd.concat(dataframes_to_merge, ignore_index=True)

        print(f"  ✓ Merged data: {len(combined)} total records")
        print(f"    BACI: {len(baci_final)} records")
        print(f"    COMTRADE: {len(comtrade_final)} records")

        # Check if COMTRADE data is aggregate
        if 'Data_Level' in comtrade_data.columns and len(comtrade_data) > 0:
            if comtrade_data['Data_Level'].iloc[0] == 'Aggregate':
                print(f"  ⚠ NOTE: COMTRADE data is at AGGREGATE LEVEL (no subcategory breakdown available)")

        return combined

    def detect_zero_values(self, data, metric):
        """Detect partners with zero values in the chosen metric"""
        # Filter out World total and aggregate
        partners_only = data[data['Partner_Code'] != 0].copy()

        # Aggregate by partner (sum across all periods)
        partner_totals = partners_only.groupby(['Partner_Code', 'Partner_Name'])[metric].sum().reset_index()

        # Find zero-value partners
        zero_value_partners = partner_totals[partner_totals[metric] == 0]

        if len(zero_value_partners) > 0:
            return zero_value_partners[['Partner_Name', metric]].copy()
        else:
            return None

    def aggregate_subcategories_to_partners(self, data, freq_code, metric_col='Metric_Value'):
        """Aggregate subcategory data to partner level"""
        if data is None or len(data) == 0:
            return None

        # Check if data has subcategories
        if 'Product_Code' not in data.columns:
            # Already aggregated
            return data

        # Aggregate by partner and period
        period_col = 'Year' if freq_code == 'A' else 'Period'

        # Determine which columns to aggregate
        # BACI has Trade_Value_USD and Quantity_MT
        # COMTRADE has Metric_Value
        agg_cols = {}
        if 'Trade_Value_USD' in data.columns:
            agg_cols['Trade_Value_USD'] = 'sum'
        if 'Quantity_MT' in data.columns:
            agg_cols['Quantity_MT'] = 'sum'
        if 'Metric_Value' in data.columns:
            agg_cols['Metric_Value'] = 'sum'

        if not agg_cols:
            print("  ⚠ No metric columns found in data")
            return None

        aggregated = data.groupby(['Partner_Code', 'Partner_Name', period_col]).agg(agg_cols).reset_index()

        # Preserve Source column if it exists
        if 'Source' in data.columns:
            source_col = data.groupby(['Partner_Code', 'Partner_Name', period_col])['Source'].first().reset_index()
            aggregated = aggregated.merge(source_col, on=['Partner_Code', 'Partner_Name', period_col], how='left')

        return aggregated

    def create_bar_chart(self, data, metric_col, metric_name, metric_type, reporter_name, product_desc, flow_desc, source_info):
        """Create professional bar chart for top partners using seaborn"""
        print("\nCreating professional bar chart visualization...")

        # Extract clean product description (remove code and subcategory info)
        clean_desc = self.get_clean_product_desc(product_desc)

        # Set seaborn style
        sns.set_style("whitegrid")
        sns.set_context("talk", font_scale=1.2)

        # Aggregate by partner (sum across all periods)
        partner_totals = data.groupby(['Partner_Code', 'Partner_Name'])[metric_col].sum().reset_index()

        # Filter out World total and sort
        partners_only = partner_totals[partner_totals['Partner_Code'] != 0].copy()
        top_partners = partners_only.nlargest(10, metric_col)

        # Create figure
        fig, ax = plt.subplots(figsize=(16, 10), dpi=100)
        fig.patch.set_facecolor('white')

        # Use seaborn color palette
        colors = sns.color_palette("deep", n_colors=len(top_partners))

        # Create bar chart
        bars = ax.barh(top_partners['Partner_Name'], top_partners[metric_col],
                       color=colors[0], edgecolor='white', linewidth=2)

        # Customize axes
        ax.set_xlabel(metric_name, fontsize=22, fontweight='bold', labelpad=20)
        ax.set_ylabel('Trading Partner', fontsize=22, fontweight='bold', labelpad=20)

        # Create title with clean description
        title = f"{reporter_name} - Top Trading Partners\n{flow_desc} of {clean_desc}\n{source_info}"
        ax.set_title(title, fontsize=28, fontweight='bold', pad=40)

        # Format x-axis based on metric type
        if metric_type == 'value':
            ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'${x/1e6:.1f}M' if x >= 1e6 else f'${x/1e3:.0f}K'))
        else:
            ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'{x/1e6:.1f}M' if x >= 1e6 else f'{x/1e3:.0f}K'))

        # Add value labels
        # Determine unit suffix based on metric name
        if metric_type == 'value':
            unit_suffix = ''  # $ prefix is added separately
        elif 'MT' in metric_name or metric_name == 'Quantity_MT':
            unit_suffix = ' MT'
        elif 'Kg' in metric_name or 'Weight' in metric_name:
            unit_suffix = ' Kg'
        else:
            unit_suffix = ''  # No unit for generic Quantity

        for bar in bars:
            width = bar.get_width()
            if metric_type == 'value':
                label = f'${width/1e6:.1f}M' if width >= 1e6 else f'${width/1e3:.0f}K'
            else:
                label = f'{width/1e6:.1f}M{unit_suffix}' if width >= 1e6 else f'{width/1e3:.0f}K{unit_suffix}'

            ax.text(width, bar.get_y() + bar.get_height()/2, f' {label}',
                   ha='left', va='center', fontsize=16, fontweight='bold')

        # Invert y-axis
        ax.invert_yaxis()

        sns.despine(left=True, bottom=True)
        plt.tight_layout()

        # Save figure with product code for clean filename
        reporter_safe = self.sanitize_filename(reporter_name)
        product_code = self.get_product_code_for_filename(product_desc)
        flow_short = 'imp' if flow_desc == 'Imports' else 'exp'
        metric_short = 'Val' if metric_type == 'value' else ('Qty' if metric_type == 'quantity' else 'Wgt')

        filename = f"BarChart_{reporter_safe}_{flow_short}_{product_code}_{metric_short}.png"
        filepath = self.base_dir / "output" / filename

        filepath.parent.mkdir(exist_ok=True)
        plt.savefig(filepath, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close()

        print(f"✓ Bar chart saved to: {filepath}")
        return filepath

    def create_stacked_bar_chart(self, data, partner_name, metric_col, metric_name, metric_type, reporter_name, product_desc, flow_desc, source_info):
        """Create stacked bar chart for specific partner analysis"""
        print("\nCreating professional stacked bar chart...")

        # Extract clean product description
        clean_desc = self.get_clean_product_desc(product_desc)

        # Set seaborn style
        sns.set_style("whitegrid")
        sns.set_context("talk", font_scale=1.3)

        # Get recent periods (last 10)
        period_col = 'Year' if 'Year' in data.columns else 'Period'
        periods = sorted(data[period_col].unique())[-10:]
        recent_data = data[data[period_col].isin(periods)]

        # Aggregate by period
        partner_data = recent_data[recent_data['Partner_Name'] == partner_name].groupby(period_col)[metric_col].sum()
        world_total = recent_data.groupby(period_col)[metric_col].sum()

        # Calculate rest of world
        rest_of_world = world_total - partner_data
        partner_share = (partner_data / world_total * 100).fillna(0)

        # Create figure
        fig, ax = plt.subplots(figsize=(18, 10), dpi=100)
        fig.patch.set_facecolor('white')

        x_positions = range(len(periods))
        x_labels = [str(p) for p in periods]

        # Use seaborn colors
        colors = sns.color_palette("Set2", n_colors=2)

        # Plot bars
        bars1 = ax.bar(x_positions, partner_data.reindex(periods, fill_value=0),
                       label=partner_name, color=colors[0],
                       edgecolor='white', linewidth=2.5)
        bars2 = ax.bar(x_positions, rest_of_world.reindex(periods, fill_value=0),
                       bottom=partner_data.reindex(periods, fill_value=0),
                       label='Rest of World', color=colors[1],
                       edgecolor='white', linewidth=2.5)

        # Labels
        ax.set_xlabel(period_col, fontsize=24, fontweight='bold', labelpad=20)
        ax.set_ylabel(metric_name, fontsize=24, fontweight='bold', labelpad=20)

        # Title with clean description
        title = f"{reporter_name} - {flow_desc} Trend\n{clean_desc}\nWorld Total vs {partner_name}\n{source_info}"
        ax.set_title(title, fontsize=30, fontweight='bold', pad=45)

        # Format y-axis
        if metric_type == 'value':
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'${x/1e9:.1f}B' if x >= 1e9
                                                              else f'${x/1e6:.1f}M' if x >= 1e6
                                                              else f'${x/1e3:.0f}K'))
        else:
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'{x/1e9:.1f}B' if x >= 1e9
                                                              else f'{x/1e6:.1f}M' if x >= 1e6
                                                              else f'{x/1e3:.0f}K'))

        ax.set_xticks(x_positions)
        ax.set_xticklabels(x_labels, rotation=45, ha='right', fontsize=14)

        # Add labels
        for i, bar1 in enumerate(bars1):
            if i < len(partner_share):
                partner_value = bar1.get_height()
                share_pct = partner_share.iloc[i]

                if metric_type == 'value':
                    value_label = f'${partner_value/1e6:.1f}M' if partner_value >= 1e6 else f'${partner_value/1e3:.0f}K'
                else:
                    value_label = f'{partner_value/1e6:.1f}M' if partner_value >= 1e6 else f'{partner_value/1e3:.0f}K'

                label_text = f'{value_label}\n({share_pct:.1f}%)'
                ax.text(bar1.get_x() + bar1.get_width()/2, partner_value/2,
                       label_text, ha='center', va='center',
                       fontsize=15, fontweight='bold', color='white')

        # Legend
        legend = ax.legend(loc='upper left', bbox_to_anchor=(1.01, 1.0), fontsize=18,
                          frameon=True, shadow=True)

        sns.despine(left=True, bottom=True)
        plt.tight_layout()

        # Save with product code for clean filename
        reporter_safe = self.sanitize_filename(reporter_name)
        product_code = self.get_product_code_for_filename(product_desc)
        partner_safe = self.sanitize_filename(partner_name)
        flow_short = 'imp' if flow_desc == 'Imports' else 'exp'
        metric_short = 'Val' if metric_type == 'value' else ('Qty' if metric_type == 'quantity' else 'Wgt')

        filename = f"StackedBar_{reporter_safe}_{flow_short}_{product_code}_{partner_safe}_{metric_short}.png"
        filepath = self.base_dir / "output" / filename

        filepath.parent.mkdir(exist_ok=True)
        plt.savefig(filepath, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close()

        print(f"✓ Stacked bar chart saved to: {filepath}")
        return filepath

    def export_specific_partner_results(self, data, partner_name, metric_col, metric_name, metric_type, reporter_name, product_desc, flow_desc, source_info):
        """Export specific partner analysis to CSV with year-by-year data and share for ALL metrics"""
        period_col = 'Year' if 'Year' in data.columns else 'Period'
        all_periods = sorted(data[period_col].unique())

        # Identify all available metric columns
        baci_metrics = ['Trade_Value_USD', 'Quantity_MT']
        comtrade_metrics = ['Primary_Value_USD', 'FOB_Value_USD', 'CIF_Value_USD', 'Quantity', 'Net_Weight_Kg', 'Gross_Weight_Kg']

        available_metrics = []
        for col in baci_metrics + comtrade_metrics:
            if col in data.columns:
                available_metrics.append(col)

        # Build export data with all periods and ALL available metrics
        export_rows = []
        for period in all_periods:
            row_data = {period_col: period}

            # Get partner and world data for this period
            partner_period_data = data[(data['Partner_Name'] == partner_name) & (data[period_col] == period)]
            world_period_data = data[data[period_col] == period]

            # Add all available metrics
            for metric in available_metrics:
                partner_val = partner_period_data[metric].sum() if len(partner_period_data) > 0 else 0
                world_val = world_period_data[metric].sum() if len(world_period_data) > 0 else 0

                row_data[f'{partner_name}_{metric}'] = partner_val
                row_data[f'World_{metric}'] = world_val

            # Calculate share based on selected metric
            partner_selected = partner_period_data[metric_col].sum() if len(partner_period_data) > 0 else 0
            world_selected = world_period_data[metric_col].sum() if len(world_period_data) > 0 else 0
            share_pct = (partner_selected / world_selected * 100) if world_selected > 0 else 0
            row_data['Partner_Share_Percent'] = round(share_pct, 2)

            export_rows.append(row_data)

        export_df = pd.DataFrame(export_rows)

        # Generate filename
        reporter_safe = self.sanitize_filename(reporter_name)
        product_code = self.get_product_code_for_filename(product_desc)
        partner_safe = self.sanitize_filename(partner_name)
        flow_short = 'imp' if flow_desc == 'Imports' else 'exp'
        metric_short = 'Val' if metric_type == 'value' else ('Qty' if metric_type == 'quantity' else 'Wgt')

        filename = f"Partner_{reporter_safe}_{flow_short}_{product_code}_{partner_safe}_{metric_short}.csv"
        filepath = self.base_dir / "output" / filename

        filepath.parent.mkdir(exist_ok=True)
        export_df.to_csv(filepath, index=False)

        print(f"\n✓ Partner analysis exported to: {filepath}")
        return filepath

    def export_results(self, data, metric_col, metric_name, metric_type, reporter_name, product_desc, flow_desc, source_info, partner_name=None):
        """Export results to CSV and .txt summary"""
        # Get product code for filename
        product_code = self.get_product_code_for_filename(product_desc)
        metric_short = 'Val' if metric_type == 'value' else ('Qty' if metric_type == 'quantity' else 'Wgt')

        # Aggregate by partner
        period_col = 'Year' if 'Year' in data.columns else 'Period'

        if partner_name:
            # For specific partner, use the dedicated function instead
            return self.export_specific_partner_results(data, partner_name, metric_col, metric_name, metric_type,
                                                        reporter_name, product_desc, flow_desc, source_info), None
        else:
            # All partners analysis - export totals by partner with ALL available metrics
            # Identify all metric columns in the data
            baci_metrics = ['Trade_Value_USD', 'Quantity_MT']
            comtrade_metrics = ['Primary_Value_USD', 'FOB_Value_USD', 'CIF_Value_USD', 'Quantity', 'Net_Weight_Kg', 'Gross_Weight_Kg', 'Metric_Value']

            # Build aggregation dict for all available metrics
            agg_dict = {}
            for col in baci_metrics + comtrade_metrics:
                if col in data.columns:
                    agg_dict[col] = 'sum'

            partner_totals = data.groupby(['Partner_Code', 'Partner_Name']).agg(agg_dict).reset_index()

            # Sort by chosen metric
            partner_totals = partner_totals.sort_values(metric_col, ascending=False)

            # Calculate World total for all metrics
            world_row_data = {
                'Partner_Code': 0,
                'Partner_Name': 'World (TOTAL - calculated)'
            }
            for col in agg_dict.keys():
                world_row_data[col] = partner_totals[partner_totals['Partner_Code'] != 0][col].sum()

            world_row = pd.DataFrame([world_row_data])

            # Combine partner totals with world row
            if len(partner_totals) > 0:
                export_data = pd.concat([partner_totals, world_row], ignore_index=True)
            else:
                export_data = world_row

        # Generate filename with product code
        reporter_safe = self.sanitize_filename(reporter_name)
        flow_short = 'imp' if flow_desc == 'Imports' else 'exp'
        base_filename = f"AllPartners_{reporter_safe}_{flow_short}_{product_code}_{metric_short}"

        # Save CSV
        csv_filename = base_filename + ".csv"
        csv_filepath = self.base_dir / "output" / csv_filename

        csv_filepath.parent.mkdir(exist_ok=True)
        export_data.to_csv(csv_filepath, index=False)

        print(f"\n✓ Results exported to: {csv_filepath}")

        # Create .txt summary
        txt_filename = base_filename + "_Summary.txt"
        txt_filepath = self.base_dir / "output" / txt_filename

        with open(txt_filepath, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("HYBRID TRADE DATA ANALYSIS SUMMARY\n")
            f.write("="*70 + "\n\n")

            f.write("ANALYSIS PARAMETERS\n")
            f.write("-"*70 + "\n")
            f.write(f"Data Source:        {source_info}\n")
            f.write(f"Reporter:           {reporter_name}\n")
            f.write(f"Product:            {product_desc}\n")
            f.write(f"Trade Direction:    {flow_desc}\n")
            f.write(f"Metric:             {metric_name}\n")

            if partner_name:
                f.write(f"Partner:            {partner_name}\n")
            else:
                partners_count = len(export_data[export_data['Partner_Code'] != 0])
                f.write(f"Total Partners:     {partners_count}\n")

            f.write("\n")

            if not partner_name:
                # All partners summary
                f.write("WORLD TOTAL\n")
                f.write("-"*70 + "\n")
                world_row = export_data[export_data['Partner_Code'] == 0]
                if not world_row.empty:
                    f.write(f"  {metric_name}:  {world_row[metric_col].iloc[0]:,.2f}\n")
                f.write("\n")

                f.write("TOP 10 TRADING PARTNERS\n")
                f.write("-"*70 + "\n")
                top_10 = export_data[export_data['Partner_Code'] != 0].head(10)
                for idx, row in top_10.iterrows():
                    rank = list(top_10.index).index(idx) + 1
                    partner = row['Partner_Name']
                    value = row[metric_col]

                    if metric_type == 'value':
                        f.write(f"  {rank:2d}. {partner:40s} ${value:,.2f}\n")
                    else:
                        f.write(f"  {rank:2d}. {partner:40s} {value:,.2f}\n")

            f.write("\n" + "="*70 + "\n")
            f.write("End of Summary\n")
            f.write("="*70 + "\n")

        print(f"✓ Summary exported to: {txt_filepath}")

        return csv_filepath, txt_filepath

    def analyze_subcategories(self, data, partner_name, metric_col):
        """Analyze top subcategories for specific partner"""
        # Filter for specific partner
        partner_data = data[data['Partner_Name'] == partner_name].copy()

        if len(partner_data) == 0:
            return None

        # Filter to only include valid HS codes (2, 4, or 6 digits)
        # This excludes COMTRADE's intermediate 5-digit aggregation codes
        partner_data['code_length'] = partner_data['Product_Code'].astype(str).str.len()
        partner_data = partner_data[partner_data['code_length'].isin([2, 4, 6])].copy()

        if len(partner_data) == 0:
            print("  ⚠ No valid HS subcategories found")
            return None

        # Aggregate by product code using the selected metric column
        agg_dict = {metric_col: 'sum'}
        subcategory_totals = partner_data.groupby(['Product_Code', 'Product_Desc']).agg(agg_dict).reset_index()

        # Sort by chosen metric (return ALL subcategories sorted)
        all_subcategories = subcategory_totals.sort_values(metric_col, ascending=False).reset_index(drop=True)

        return all_subcategories

    def create_subcategory_bar_chart(self, subcategory_data, partner_name, metric_col, metric_name, metric_type, reporter_name, product_desc, flow_desc, source_info):
        """Create bar chart for top 5 subcategories"""
        print("\nCreating subcategory bar chart...")

        # Use only top 5 for chart
        chart_data = subcategory_data.head(5)

        # Extract clean product description
        clean_desc = self.get_clean_product_desc(product_desc)

        # Set seaborn style
        sns.set_style("whitegrid")
        sns.set_context("talk", font_scale=1.2)

        # Create figure
        fig, ax = plt.subplots(figsize=(16, 12), dpi=100)
        fig.patch.set_facecolor('white')

        # Use seaborn color palette
        colors = sns.color_palette("deep", n_colors=len(chart_data))

        # Create labels (truncate long descriptions)
        labels = []
        for _, row in chart_data.iterrows():
            code = row['Product_Code']
            desc = row['Product_Desc']
            if len(str(desc)) > 50:
                desc = str(desc)[:47] + "..."
            labels.append(f"{code} - {desc}")

        # Create bar chart
        bars = ax.barh(labels, chart_data[metric_col],
                       color=colors[0], edgecolor='white', linewidth=2)

        # Customize axes
        ax.set_xlabel(metric_name, fontsize=22, fontweight='bold', labelpad=20)
        ax.set_ylabel('Product Subcategory', fontsize=22, fontweight='bold', labelpad=20)

        # Create title with clean description
        title = f"{reporter_name} - Top Product Subcategories\n{flow_desc} of {clean_desc} with {partner_name}\n{source_info}"
        ax.set_title(title, fontsize=28, fontweight='bold', pad=40)

        # Format x-axis
        if metric_type == 'value':
            ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'${x/1e6:.1f}M' if x >= 1e6 else f'${x/1e3:.0f}K'))
        else:
            ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'{x/1e6:.1f}M' if x >= 1e6 else f'{x/1e3:.0f}K'))

        # Add value labels
        for bar in bars:
            width = bar.get_width()
            if metric_type == 'value':
                label = f'${width/1e6:.1f}M' if width >= 1e6 else f'${width/1e3:.0f}K'
            else:
                label = f'{width/1e6:.1f}M' if width >= 1e6 else f'{width/1e3:.0f}K'

            ax.text(width, bar.get_y() + bar.get_height()/2, f' {label}',
                   ha='left', va='center', fontsize=16, fontweight='bold')

        # Invert y-axis
        ax.invert_yaxis()

        sns.despine(left=True, bottom=True)
        plt.tight_layout()

        # Save figure with product code for clean filename
        reporter_safe = self.sanitize_filename(reporter_name)
        product_code = self.get_product_code_for_filename(product_desc)
        partner_safe = self.sanitize_filename(partner_name)
        flow_short = 'imp' if flow_desc == 'Imports' else 'exp'
        metric_short = 'Val' if metric_type == 'value' else ('Qty' if metric_type == 'quantity' else 'Wgt')

        filename = f"Subcats_{reporter_safe}_{flow_short}_{product_code}_{partner_safe}_{metric_short}.png"
        filepath = self.base_dir / "output" / filename

        filepath.parent.mkdir(exist_ok=True)
        plt.savefig(filepath, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close()

        print(f"✓ Subcategory bar chart saved to: {filepath}")
        return filepath

    def export_subcategory_results(self, subcategory_data, partner_name, metric_col, metric_name, metric_type, reporter_name, product_desc, flow_desc, source_info):
        """Export subcategory analysis to CSV with totals"""
        # Add total row to CSV
        export_data = subcategory_data.copy()
        total_row = pd.DataFrame([{
            'Product_Code': 'TOTAL',
            'Product_Desc': 'Total (all subcategories)',
            metric_col: export_data[metric_col].sum()
        }])
        # Combine export data with total row
        if len(export_data) > 0:
            export_data = pd.concat([export_data, total_row], ignore_index=True)
        else:
            export_data = total_row

        # Generate clean filename
        reporter_safe = self.sanitize_filename(reporter_name)
        product_code = self.get_product_code_for_filename(product_desc)
        partner_safe = self.sanitize_filename(partner_name)
        flow_short = 'imp' if flow_desc == 'Imports' else 'exp'
        metric_short = 'Val' if metric_type == 'value' else ('Qty' if metric_type == 'quantity' else 'Wgt')

        csv_filename = f"Subcats_{reporter_safe}_{flow_short}_{product_code}_{partner_safe}_{metric_short}.csv"
        csv_filepath = self.base_dir / "output" / csv_filename

        csv_filepath.parent.mkdir(exist_ok=True)
        export_data.to_csv(csv_filepath, index=False)

        print(f"✓ Subcategory results exported to: {csv_filepath}")

        return csv_filepath

    def export_consolidated_summary(self, combined_data, subcategory_data, partner_name, metric_col, metric_name, metric_type,
                                    reporter_name, product_desc, flow_desc, source_info):
        """Export ONE consolidated summary file with all terminal output"""
        # Generate clean filename
        reporter_safe = self.sanitize_filename(reporter_name)
        product_code = self.get_product_code_for_filename(product_desc)
        partner_safe = self.sanitize_filename(partner_name)
        flow_short = 'imp' if flow_desc == 'Imports' else 'exp'
        metric_short = 'Val' if metric_type == 'value' else ('Qty' if metric_type == 'quantity' else 'Wgt')

        txt_filename = f"Summary_{reporter_safe}_{flow_short}_{product_code}_{partner_safe}_{metric_short}.txt"
        txt_filepath = self.base_dir / "output" / txt_filename

        txt_filepath.parent.mkdir(exist_ok=True)

        with open(txt_filepath, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("HYBRID TRADE DATA ANALYSIS - COMPLETE SUMMARY\n")
            f.write("="*70 + "\n\n")

            f.write("ANALYSIS PARAMETERS\n")
            f.write("-"*70 + "\n")
            f.write(f"Data Source:        {source_info}\n")
            f.write(f"Reporter:           {reporter_name}\n")
            f.write(f"Product:            {product_desc}\n")
            f.write(f"Trade Direction:    {flow_desc}\n")
            f.write(f"Partner:            {partner_name}\n")
            f.write(f"Metric:             {metric_name}\n\n")

            # Calculate and write totals
            partner_data = combined_data[combined_data['Partner_Name'] == partner_name]
            total_partner = partner_data[metric_col].sum()
            total_world = combined_data[metric_col].sum()
            share = (total_partner / total_world * 100) if total_world > 0 else 0

            f.write("="*70 + "\n")
            f.write(f"SPECIFIC PARTNER ANALYSIS: {partner_name}\n")
            f.write("="*70 + "\n\n")

            f.write(f"Partner Total ({metric_name}): ")
            if metric_type == 'value':
                f.write(f"${total_partner:,.2f}\n")
            else:
                f.write(f"{total_partner:,.2f}\n")

            f.write(f"World Total ({metric_name}): ")
            if metric_type == 'value':
                f.write(f"${total_world:,.2f}\n")
            else:
                f.write(f"{total_world:,.2f}\n")

            f.write(f"Partner Share: {share:.2f}%\n\n")

            # Write recent periods data
            period_col = 'Year' if 'Year' in combined_data.columns else 'Period'
            periods = sorted(combined_data[period_col].unique())[-10:]

            f.write("-"*70 + "\n")
            f.write(f"RECENT {len(periods)} PERIODS - PARTNER PERFORMANCE:\n")
            f.write("-"*70 + "\n\n")

            partner_by_period = partner_data.groupby(period_col)[metric_col].sum()
            world_by_period = combined_data.groupby(period_col)[metric_col].sum()

            f.write(f"{period_col:12s}  {partner_name:20s}  {'World Total':20s}  {'Share %':>10s}\n")
            f.write("-"*70 + "\n")

            for period in periods:
                partner_val = partner_by_period.get(period, 0)
                world_val = world_by_period.get(period, 0)
                share_pct = (partner_val / world_val * 100) if world_val > 0 else 0

                if metric_type == 'value':
                    partner_str = f"${partner_val:,.2f}"
                    world_str = f"${world_val:,.2f}"
                else:
                    partner_str = f"{partner_val:,.2f}"
                    world_str = f"{world_val:,.2f}"

                f.write(f"{str(period):12s}  {partner_str:20s}  {world_str:20s}  {share_pct:9.2f}%\n")

            # Write subcategory analysis
            if subcategory_data is not None and len(subcategory_data) > 0:
                f.write("\n" + "="*70 + "\n")
                f.write("SUBCATEGORY ANALYSIS\n")
                f.write("="*70 + "\n\n")

                f.write(f"Total Subcategories: {len(subcategory_data)}\n\n")
                f.write(f"Top 10 Product Subcategories (by {metric_name}):\n")
                f.write("-"*70 + "\n\n")

                # Display top 10 in txt file
                top_10 = subcategory_data.head(10)

                for idx, row in top_10.iterrows():
                    rank = idx + 1
                    code = row['Product_Code']
                    desc = row['Product_Desc']

                    f.write(f"{rank:2d}. {code} - {desc}\n")

                    # Handle both BACI (Trade_Value_USD, Quantity_MT) and COMTRADE (Metric_Value) columns
                    if 'Trade_Value_USD' in row and 'Quantity_MT' in row:
                        # BACI data - show both value and quantity
                        if metric_name == 'Trade_Value_USD':
                            f.write(f"    Trade Value: ${row['Trade_Value_USD']:,.2f}\n")
                            f.write(f"    Quantity:    {row['Quantity_MT']:,.2f} MT\n")
                        else:
                            f.write(f"    Quantity:    {row['Quantity_MT']:,.2f} MT\n")
                            f.write(f"    Trade Value: ${row['Trade_Value_USD']:,.2f}\n")
                    elif 'Metric_Value' in row:
                        # COMTRADE data - show metric value with appropriate formatting
                        if metric_type == 'value':
                            f.write(f"    {metric_name}: ${row['Metric_Value']:,.2f}\n")
                        else:
                            f.write(f"    {metric_name}: {row['Metric_Value']:,.2f}\n")
                    else:
                        # Fallback - use metric_col
                        val = row.get(metric_col, 0)
                        if metric_type == 'value':
                            f.write(f"    {metric_name}: ${val:,.2f}\n")
                        else:
                            f.write(f"    {metric_name}: {val:,.2f}\n")
                    f.write("\n")

            f.write("="*70 + "\n")
            f.write("End of Analysis Summary\n")
            f.write("="*70 + "\n")

        print(f"✓ Complete analysis summary exported to: {txt_filepath}")
        return txt_filepath

    def run(self):
        """Main execution flow"""
        print("\n" + "="*60)
        print("INTERNATIONAL TRADE DATA ANALYSIS TOOL")
        print("="*60)
        print("Available Data Sources:")
        print("  BACI      :  1995-2024 (harmonized bilateral flows, annual)")
        print("  COMTRADE  :  1962-present (as reported, annual and monthly)")
        print("="*60)

        # Get user inputs
        freq_code = self.get_frequency_input()
        data_source = self.get_data_source_input(freq_code)
        period = self.get_period_input(freq_code, data_source)
        reporter_code, reporter_name, reporter_baci_code = self.get_country_input("reporter")
        cmd_code, product_desc = self.get_product_input()
        flow_code, flow_desc = self.get_trade_direction()
        partner_choice, partner_code, partner_name, partner_baci_code = self.get_partner_choice()

        # Determine years/periods for source info
        if freq_code == 'A':
            years = [int(y) for y in period.split(',')] if ',' in period else [int(period)]
            source_info = f"{data_source} ({min(years)}-{max(years)})" if len(years) > 1 else f"{data_source} ({years[0]})"
        else:
            years = None
            source_info = f"{data_source} ({period})"

        # For specific partner analysis, load with subcategories and aggregate later
        keep_subs = (partner_choice == 'specific')

        data_subcategories = None
        metric_name = None
        metric_type = None
        metric_col = None

        if data_source == 'BACI':
            # BACI: Get metric choice first (only V and Q available)
            metric_name, metric_type, metric_col = self.get_metric_choice_baci()

            print("\n" + "="*60)
            print("ANALYSIS CONFIGURATION")
            print("="*60)
            print(f"Data Source:     {data_source}")
            print(f"Frequency:       {'Annual' if freq_code == 'A' else 'Monthly'}")
            print(f"Period:          {period.replace(',', ', ') if ',' in period else period}")
            print(f"Reporter:        {reporter_name}")
            print(f"Product:         {product_desc}")
            print(f"Direction:       {flow_desc}")
            print(f"Analysis Type:   {'All Partners' if partner_choice == 'all' else f'Specific Partner: {partner_name}'}")
            print(f"Metric:          {metric_name}")
            print("="*60)

            # Load BACI data
            data_subcategories = self.load_baci_data(years, reporter_baci_code, cmd_code, flow_code, keep_subcategories=keep_subs)

        else:
            # COMTRADE: Fetch data first, then show available metrics
            print("\n" + "="*60)
            print("FETCHING DATA")
            print("="*60)
            print(f"Data Source:     {data_source}")
            print(f"Frequency:       {'Annual' if freq_code == 'A' else 'Monthly'}")
            print(f"Period:          {period.replace(',', ', ') if ',' in period else period}")
            print(f"Reporter:        {reporter_name}")
            print(f"Product:         {product_desc}")
            print(f"Direction:       {flow_desc}")
            print("="*60)

            raw_comtrade = self.fetch_comtrade_data(freq_code, period, reporter_code, cmd_code, flow_code, partner_code if partner_choice == 'specific' else None)

            if raw_comtrade is None or len(raw_comtrade) == 0:
                print("\n✗ Analysis cancelled: No data returned from COMTRADE API")
                return

            # Get available metrics from the API response
            available_metrics = self.get_comtrade_available_metrics(raw_comtrade)

            if not available_metrics:
                print("\n✗ Analysis cancelled: No metrics available in COMTRADE response")
                return

            # Let user choose from available metrics
            metric_name, metric_type, metric_col = self.get_metric_choice_comtrade(available_metrics)

            if metric_col is None:
                print("\n✗ Analysis cancelled: No metric selected")
                return

            print("\n" + "="*60)
            print("ANALYSIS CONFIGURATION")
            print("="*60)
            print(f"Data Source:     {data_source}")
            print(f"Frequency:       {'Annual' if freq_code == 'A' else 'Monthly'}")
            print(f"Period:          {period.replace(',', ', ') if ',' in period else period}")
            print(f"Reporter:        {reporter_name}")
            print(f"Product:         {product_desc}")
            print(f"Direction:       {flow_desc}")
            print(f"Analysis Type:   {'All Partners' if partner_choice == 'all' else f'Specific Partner: {partner_name}'}")
            print(f"Metric:          {metric_name} ({metric_col})")
            print("="*60)

            # Process COMTRADE data with selected metric
            data_subcategories = self.process_comtrade_data(raw_comtrade, freq_code, metric_col, keep_subcategories=keep_subs)

        # Aggregate subcategory data for partner-level analysis
        combined_data = self.aggregate_subcategories_to_partners(data_subcategories, freq_code)

        if combined_data is None or len(combined_data) == 0:
            print("\n✗ Analysis cancelled: No data available from any source")
            return

        # Determine the actual metric column in the data
        # BACI has Trade_Value_USD and Quantity_MT
        # COMTRADE has Metric_Value
        if data_source == 'BACI':
            actual_metric_col = metric_name  # Trade_Value_USD or Quantity_MT
        else:
            actual_metric_col = 'Metric_Value'

        # Analyze based on partner choice
        if partner_choice == 'all':
            # All partners analysis
            print(f"\n{'='*60}")
            print("ALL PARTNERS ANALYSIS")
            print(f"{'='*60}")

            # Aggregate totals using actual metric column
            partner_totals = combined_data.groupby(['Partner_Code', 'Partner_Name']).agg({
                actual_metric_col: 'sum'
            }).reset_index()

            # Calculate World total
            world_total = partner_totals[partner_totals['Partner_Code'] != 0][actual_metric_col].sum()

            print(f"\nTotal Trading Partners: {len(partner_totals[partner_totals['Partner_Code'] != 0])}")
            print(f"World Total ({metric_name}): ", end='')
            if metric_type == 'value':
                print(f"${world_total:,.2f}")
            else:
                print(f"{world_total:,.2f}")

            # Display top 10 partners in terminal
            print(f"\n{'-'*60}")
            print(f"TOP 10 TRADING PARTNERS (by {metric_name}):")
            print(f"{'-'*60}")

            top_10 = partner_totals[partner_totals['Partner_Code'] != 0].nlargest(10, actual_metric_col)

            # Create display dataframe
            display_df = top_10[['Partner_Name', actual_metric_col]].copy()

            # Format values for display
            if metric_type == 'value':
                display_df[actual_metric_col] = display_df[actual_metric_col].apply(lambda x: f"${x:,.2f}")
            else:
                display_df[actual_metric_col] = display_df[actual_metric_col].apply(lambda x: f"{x:,.2f}")

            # Rename columns for display
            display_df.columns = ['Partner', metric_name]

            print(display_df.to_string(index=False))
            print(f"{'-'*60}")

            # Detect zero values
            zero_values = self.detect_zero_values(combined_data, actual_metric_col)
            if zero_values is not None and len(zero_values) > 0:
                print(f"\n{'='*60}")
                print("DATA QUALITY WARNING")
                print(f"{'='*60}")
                print(f"{len(zero_values)} partners have ZERO values for {metric_name}:")
                print(f"{'-'*60}")
                for idx, row in zero_values.head(20).iterrows():
                    print(f"  • {row['Partner_Name']}")
                if len(zero_values) > 20:
                    print(f"  ... and {len(zero_values) - 20} more")
                print(f"{'-'*60}")
                print("Note: This may indicate incomplete reporting in the database.")
                print(f"{'='*60}")

            # Export results
            csv_file, txt_file = self.export_results(combined_data, actual_metric_col, metric_name, metric_type,
                                                     reporter_name, product_desc, flow_desc, source_info)

            # Create visualization
            self.create_bar_chart(combined_data, actual_metric_col, metric_name, metric_type,
                                 reporter_name, product_desc, flow_desc, source_info)

        else:
            # Specific partner analysis
            print(f"\n{'='*60}")
            print(f"SPECIFIC PARTNER ANALYSIS: {partner_name}")
            print(f"{'='*60}")

            # Filter for specific partner
            partner_data = combined_data[combined_data['Partner_Name'] == partner_name]

            if len(partner_data) == 0:
                print(f"\n✗ No data found for {partner_name}")
                return

            # Calculate totals
            total_partner = partner_data[actual_metric_col].sum()
            total_world = combined_data[actual_metric_col].sum()
            share = (total_partner / total_world * 100) if total_world > 0 else 0

            print(f"\nPartner Total ({metric_name}): ", end='')
            if metric_type == 'value':
                print(f"${total_partner:,.2f}")
            else:
                print(f"{total_partner:,.2f}")

            print(f"World Total ({metric_name}): ", end='')
            if metric_type == 'value':
                print(f"${total_world:,.2f}")
            else:
                print(f"{total_world:,.2f}")

            print(f"Partner Share: {share:.2f}%")

            # Display recent periods in terminal
            period_col = 'Year' if 'Year' in combined_data.columns else 'Period'
            periods = sorted(combined_data[period_col].unique())[-10:]
            recent_data = combined_data[combined_data[period_col].isin(periods)]

            print(f"\n{'-'*60}")
            print(f"RECENT {len(periods)} PERIODS - PARTNER PERFORMANCE:")
            print(f"{'-'*60}")

            # Aggregate by period
            partner_by_period = recent_data[recent_data['Partner_Name'] == partner_name].groupby(period_col)[actual_metric_col].sum()
            world_by_period = recent_data.groupby(period_col)[actual_metric_col].sum()

            # Create display dataframe
            display_data = []
            for period in periods:
                partner_val = partner_by_period.get(period, 0)
                world_val = world_by_period.get(period, 0)
                share_pct = (partner_val / world_val * 100) if world_val > 0 else 0

                if metric_type == 'value':
                    partner_str = f"${partner_val:,.2f}"
                    world_str = f"${world_val:,.2f}"
                else:
                    partner_str = f"{partner_val:,.2f}"
                    world_str = f"{world_val:,.2f}"

                display_data.append({
                    period_col: period,
                    f'{partner_name}': partner_str,
                    'World Total': world_str,
                    'Share %': f"{share_pct:.2f}%"
                })

            display_df = pd.DataFrame(display_data)
            print(display_df.to_string(index=False))
            print(f"{'-'*60}")

            # Create visualization
            self.create_stacked_bar_chart(combined_data, partner_name, actual_metric_col, metric_name, metric_type,
                                          reporter_name, product_desc, flow_desc, source_info)

            # Export specific partner year-by-year data with share
            self.export_specific_partner_results(combined_data, partner_name, actual_metric_col, metric_name, metric_type,
                                                  reporter_name, product_desc, flow_desc, source_info)

            # Subcategory analysis for specific partner
            print(f"\n{'='*60}")
            print("SUBCATEGORY ANALYSIS")
            print(f"{'='*60}")

            # Determine subcategory metric column
            if data_source == 'BACI':
                sub_metric_col = metric_name
            else:
                sub_metric_col = 'Metric_Value'

            # Use subcategory data from the selected source
            if data_subcategories is not None and len(data_subcategories) > 0:
                # Analyze top subcategories
                top_subcategories = self.analyze_subcategories(data_subcategories, partner_name, sub_metric_col)

                if top_subcategories is not None and len(top_subcategories) > 0:
                    # Display top 10 in terminal
                    display_top_10 = top_subcategories.head(10)

                    print(f"\nTop 10 Product Subcategories (by {metric_name}):")
                    print(f"{'-'*60}")

                    # Display in terminal
                    display_df = display_top_10[['Product_Code', 'Product_Desc', sub_metric_col]].copy()

                    # Format values
                    if metric_type == 'value':
                        display_df[sub_metric_col] = display_df[sub_metric_col].apply(lambda x: f"${x:,.2f}")
                    else:
                        display_df[sub_metric_col] = display_df[sub_metric_col].apply(lambda x: f"{x:,.2f}")

                    # Rename for display
                    display_df.columns = ['Code', 'Description', metric_name]

                    # Truncate long descriptions for terminal
                    display_df['Description'] = display_df['Description'].apply(lambda x: str(x)[:50] + "..." if len(str(x)) > 50 else str(x))

                    print(display_df.to_string(index=False))
                    print(f"{'-'*60}")

                    # Export subcategory results to CSV
                    self.export_subcategory_results(top_subcategories, partner_name, sub_metric_col, metric_name, metric_type,
                                                    reporter_name, product_desc, flow_desc, source_info)

                    # Create subcategory bar chart
                    self.create_subcategory_bar_chart(top_subcategories, partner_name, sub_metric_col, metric_name, metric_type,
                                                      reporter_name, product_desc, flow_desc, source_info)

                    # Export consolidated summary TXT file with all terminal output
                    self.export_consolidated_summary(combined_data, top_subcategories, partner_name, actual_metric_col, metric_name, metric_type,
                                                    reporter_name, product_desc, flow_desc, source_info)
                else:
                    print("\n⚠ No subcategory data available for analysis")
                    # Export summary without subcategory data
                    self.export_consolidated_summary(combined_data, None, partner_name, actual_metric_col, metric_name, metric_type,
                                                    reporter_name, product_desc, flow_desc, source_info)
            else:
                print("\n⚠ No subcategory data could be loaded")
                # Export summary without subcategory data
                self.export_consolidated_summary(combined_data, None, partner_name, actual_metric_col, metric_name, metric_type,
                                                reporter_name, product_desc, flow_desc, source_info)

        print(f"\n{'='*60}")
        print("ANALYSIS COMPLETE")
        print(f"{'='*60}\n")

        # Ask if user wants another analysis
        print("Run another analysis?")
        print("  Y  or  Yes  :  Start a new analysis")
        print("  N  or  No   :  Exit the program")
        print("")
        another = input("Enter choice: ").strip().upper()
        if another in ['Y', 'YES']:
            print("\n" * 2)
            self.run()


if __name__ == "__main__":
    try:
        analyzer = TradeAnalyzer()
        analyzer.run()
    except KeyboardInterrupt:
        print("\n\nAnalysis cancelled by user.")
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
