from sqlalchemy import text
from tqdm import tqdm

import pandas as pd
import datetime
import gc

from smartmeter.config import DATA_DIR, SAMPLES_DIR
from smartmeter.db import get_engine

def main():
    connection = get_engine()
    steps = [
        ('DimDate', createAndFillDimDate),
        ('DimTime', createAndFillDimTime),
        ('DimWeatherStation', readAndFillDimWeatherStation),
        ('DimUser', createAndFillDimUser),
        ('FactEnergyUsage', createAndWriteFactEnergyUsage),
        ('DimNetAdministrator', readAndFillDimNetAdministrator),
        ('FactDistributionCost', readAndFillFactDistributionCost),
        ('FactContribution', readAndFillFactContribution),
        ('DimContract', createAndFillDimContract),
        ('FactEnergyCost', readAndFillFactEnergyCost),
    ]
    for table, step in steps:
        with connection.connect() as conn:
            if conn.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar() == 0:
                step(connection)
            else:
                print(f'{table}: already filled, skipping\n')
    print('\nDone.')

def createAndFillDimDate(connection):
    print('Creating DimDate table...')
    date_range = pd.date_range(start=datetime.date(2010, 1, 1), end=datetime.date(2030, 12, 31)) 

    days_dutch = {'Monday': 'maandag', 'Tuesday': 'dinsdag', 'Wednesday': 'woensdag', 'Thursday': 'donderdag', 'Friday': 'vrijdag', 'Saturday': 'zaterdag', 'Sunday': 'zondag'}
    months_dutch = {'January': 'januari', 'February': 'februari', 'March': 'maart', 'April': 'april', 'May': 'mei', 'June': 'juni', 'July': 'juli', 'August': 'augustus', 'September': 'september', 'October': 'oktober', 'November': 'november', 'December': 'december'}
    quarters = {1: "First", 2: "Second", 3: "Third", 4: "Fourth"}

    dimDate = pd.DataFrame(date_range, columns=['FullDateAlternateKey'])
    dimDate['DateKey'] = dimDate['FullDateAlternateKey'].dt.strftime('%Y%m%d').astype(int)
    dimDate['DayOfMonth'] = dimDate['FullDateAlternateKey'].dt.day
    dimDate['NameDayOfWeekEN'] = dimDate['FullDateAlternateKey'].dt.strftime('%A')
    dimDate['NameDayOfWeekDutch'] = dimDate['NameDayOfWeekEN'].map(days_dutch)
    dimDate['DayOfWeek'] = dimDate['FullDateAlternateKey'].dt.dayofweek + 1
    dimDate['DayOfWeekInMonth'] = (dimDate['FullDateAlternateKey'].dt.day - 1) // 7 + 1
    dimDate['DayOfWeekInYear'] = (dimDate['FullDateAlternateKey'].dt.dayofyear - 1) // 7 + 1
    dimDate['WeekOfYear'] = dimDate['FullDateAlternateKey'].dt.strftime('%U').astype(int) + 1
    dimDate['Month'] = dimDate['FullDateAlternateKey'].dt.month
    dimDate['NameMonthEN'] = dimDate['FullDateAlternateKey'].dt.strftime('%B')
    dimDate['NameMonthDutch'] = dimDate['NameMonthEN'].map(months_dutch)
    dimDate['MonthOfQuarter'] = (dimDate['FullDateAlternateKey'].dt.month - 1) % 4
    dimDate['Quarter'] = dimDate['FullDateAlternateKey'].dt.quarter
    dimDate['QuarterName'] = dimDate['FullDateAlternateKey'].dt.quarter.map(quarters)
    dimDate['Year'] = dimDate['FullDateAlternateKey'].dt.year
    dimDate['MonthYear'] = dimDate['FullDateAlternateKey'].dt.strftime('%b-%Y')
    dimDate['MMYYYY'] = dimDate['FullDateAlternateKey'].dt.strftime('%m%Y')
    dimDate['DayOfYear'] = dimDate['FullDateAlternateKey'].dt.dayofyear
    dimDate['DayOfQuarter'] = dimDate.groupby(['Year', 'Quarter']).cumcount() // 7 + 1
    dimDate['WeekOfMonth'] = (dimDate['FullDateAlternateKey'].dt.day - 1) // 7 + 1
    dimDate['WeekOfQuarter'] = ((dimDate['FullDateAlternateKey'].dt.dayofyear - 1) // 7 + 1) - (dimDate['Quarter'] - 1) * 13

    try:
        dimDate.to_sql('DimDate', con=connection, if_exists='append', index=False) 
        print('DimDate table created\n')
    except Exception:
        raise
    return

def createAndFillDimTime(connection):
    print('Creating DimTime table...')
    time_range = pd.date_range(start='00:00', end='23:59', freq='1min') 

    dimTime = pd.DataFrame({ 
      "FullTime": time_range.strftime('%H:%M:%S'),
      "Hour": time_range.strftime('%H'),
      "Minute": time_range.strftime('%M'),
      "Second": time_range.strftime('%S'),
      "AMPM": time_range.strftime('%I:%M %p'),
    })

    try:
        dimTime.to_sql('DimTime', con=connection, if_exists='append', index=False) 
        print('DimTime table created\n')
    except Exception:
        raise
    return

def readAndFillDimWeatherStation(connection):
    print('Creating DimWeatherStation table...')
    dimWeatherStation = pd.read_csv(f'{DATA_DIR}/input/aws_station.csv', sep=',') 
    dimWeatherStation.drop(columns=['FID', 'date_begin', 'date_end'], inplace=True) 
    dimWeatherStation.rename(columns={'code': 'WeatherStationID', 'name': 'WeatherStationName', 'altitude': 'Altitude'}, inplace=True)

    dimWeatherStation[['Latitude', 'Longitude']] = dimWeatherStation['the_geom'].str.lstrip('POINT (').str.rstrip(')').str.split(' ', expand=True)
    dimWeatherStation.drop(columns=['the_geom'], inplace=True)

    try:
        dimWeatherStation.to_sql('DimWeatherStation', con=connection, if_exists='append', index=False)
        print('DimWeatherStation created\n')
    except Exception:
        raise
    return

def createAndFillDimUser(connection):
    print('Creating DimUser table...')
    sample_files = list(SAMPLES_DIR.glob('*.csv'))
    df_list = []
    for file in tqdm(sample_files, desc="Processing DimUser CSVs", unit="file"):
        df = pd.read_csv(
            file,
            sep=',',
            usecols=['EAN_ID', 'Warmtepomp_Indicator', 'Elektrisch_Voertuig_Indicator', 'PV_Installatie_Indicator', 'Contract_Categorie'],
            dtype={'EAN_ID': 'int32', 'Warmtepomp_Indicator': 'int8', 'Elektrisch_Voertuig_Indicator': 'int8', 'PV_Installatie_Indicator': 'int8'},
            low_memory=False
        )
        df_list.append(df)

    dimUser = pd.concat(df_list, ignore_index=True)
    dimUser.rename(columns={
        'Warmtepomp_Indicator': 'HeatPumpIndicator', 
        'Elektrisch_Voertuig_Indicator': 'ElectricVehicleIndicator', 
        'PV_Installatie_Indicator': 'PVInstallationIndicator', 
        'Contract_Categorie': 'ContractType'
    }, inplace=True)
    dimUser.drop_duplicates(subset=['EAN_ID'], keep='first', inplace=True)

    try:
        dimUser.to_sql('DimUser', con=connection, if_exists='append', index=False)
        print('DimUser created\n')
    except Exception:
        raise
    return

def createAndWriteFactEnergyUsage(connection):
    print('Creating FactEnergyUsage table...')
    sample_files = list(SAMPLES_DIR.glob('*.csv'))
    dimTime = pd.read_sql('SELECT TimeKey, FullTime FROM DimTime', con=connection)
    dimUsers = pd.read_sql('SELECT UserKey, EAN_ID FROM DimUser', con=connection)

    temp_csv_path = DATA_DIR / "temp_fact_energy_usage.csv"
    if temp_csv_path.exists():
        temp_csv_path.unlink()

    for file in tqdm(sample_files, desc="Processing FactEnergyUsage CSVs", unit="file"):
        df = pd.read_csv(
            file,
            sep=',',
            usecols=['EAN_ID', 'Datum', 'Datum_Startuur', 'Volume_Afname_KWh', 'Volume_Injectie_KWh'],
            dtype={'EAN_ID': 'int32', 'Volume_Afname_KWh': 'float32', 'Volume_Injectie_KWh': 'float32'},
            low_memory=False
        )
        df.rename(columns={
            'Datum': 'DateKey',
            'Datum_Startuur': 'FullTime',
            'Volume_Afname_KWh': 'Usage_kWh',
            'Volume_Injectie_KWh': 'Injection_kWh',
        }, inplace=True)

        dt_date = pd.to_datetime(df['DateKey'], format='%Y-%m-%d')
        df['DateKey'] = dt_date.dt.strftime('%Y%m%d').astype('int32')
        df['month'] = dt_date.dt.month.astype('int8')
        df['DayOfWeek'] = dt_date.dt.dayofweek.astype('int8')

        dt_time = pd.to_datetime(df['FullTime'], format='%Y-%m-%dT%H:%M:%S.%fZ')
        df['FullTime'] = dt_time.dt.strftime('%H:%M:%S')
        df['HourOfDay'] = dt_time.dt.hour.astype('int8')

        df = df.merge(dimTime, how='inner', on='FullTime')
        df = df.merge(dimUsers, how='inner', on='EAN_ID')
        df.drop(columns=['EAN_ID'], inplace=True)

        monthlyPeak = df.groupby(['UserKey', 'month'])['Usage_kWh'].max() * 4
        monthlyPeak.name = 'MonthlyPeak_kW'
        df = df.merge(monthlyPeak, how='inner', on=['UserKey', 'month'])
        df.loc[df['MonthlyPeak_kW'] < 2.5, 'MonthlyPeak_kW'] = 2.5

        df['DaytimeRate'] = 0
        df.loc[(df['DayOfWeek'] <= 4) & (df['HourOfDay'].between(7, 21)), 'DaytimeRate'] = 1

        df.loc[df['Usage_kWh'] < 1e-4, 'Usage_kWh'] = 0
        df.loc[df['Injection_kWh'] < 1e-4, 'Injection_kWh'] = 0

        df = df[['DateKey', 'TimeKey', 'UserKey', 'Usage_kWh', 'Injection_kWh', 'MonthlyPeak_kW', 'DaytimeRate']]
        df.drop_duplicates(subset=['DateKey', 'TimeKey', 'UserKey'], keep='first', inplace=True)

        df.to_csv(temp_csv_path, mode='a', index=False, header=not temp_csv_path.exists(), sep=',')

        del df, dt_date, dt_time, monthlyPeak
        gc.collect()

    tqdm.write("Executing SQL BULK INSERT...")
    container_csv_path = f"/var/opt/mssql/import/data/{temp_csv_path.name}"
    with connection.begin() as conn:
        conn.execute(text(f"""
            BULK INSERT FactEnergyUsage
            FROM '{container_csv_path}'
            WITH (
                FORMAT = 'CSV',
                FIRSTROW = 2,
                FIELDTERMINATOR = ',',
                ROWTERMINATOR = '\\n',
                TABLOCK
            )"""
        ))
    tqdm.write("BULK INSERT completed.")

    if temp_csv_path.exists():
        temp_csv_path.unlink()

    print('FactEnergyUsage created\n')

def readAndFillDimNetAdministrator(connection):
    print('Creating DimNetAdministrator table...')
    dimNetAdministrator = pd.read_csv(f'{DATA_DIR}/input/Distributiekosten.csv', sep=',')

    dimNetAdministrator = pd.DataFrame(dimNetAdministrator['Intercommunale'].unique(), columns=['NetAdministratorName'])
    dimNetAdministrator['NetAdministratorID'] = dimNetAdministrator['NetAdministratorName'].map({
      'Fluvius Antwerpen': 'FLVAN',
      'Fluvius Limburg': 'FLVLI',
      'Fluvius West': 'FLVWE',
      'Gaselwest': 'GSLWE',
      'Imewo': 'IMWO',
      'Intergem': 'INTRG',
      'Iveka': 'IVKA',
      'Iverlek': 'IVRL',
      'PBE': 'PBE',
      'Sibelgas': 'SBLGS',
      'Fluvius (Antwerpen)': 'FLV(AN)',
      'Fluvius (Limburg)': 'FLV(LI)',
      'Fluvius (West)': 'FLV(WE)',
      'Fluvius (Imewo)': 'FLV(IMWO)',
      'Fluvius (Midden-Vlaanderen)': 'FLV(MVL)',
      'Fluvius (Kempen)': 'FLV(K)',
      'Fluvius (Zenne-Dijle)': 'FLV(ZD)',
      'Fluvius (Halle-Vilvoorde)': 'FLV(HV)',
    })

    try:
        dimNetAdministrator.to_sql('DimNetAdministrator', con=connection, if_exists='append', index=False) 
        print('DimNetAdministrator created\n')
    except Exception:
        raise
    return

def readAndFillFactDistributionCost(connection):
    print('Creating FactDistributionCost table...')
    factDistributionCost = pd.read_csv(f'{DATA_DIR}/input/Distributiekosten.csv', sep=',')
    factDistributionCost.rename(columns={'Capaciteitstarief_Digitale_meter': 'CapacityTariff_DigitalMeter', 'Afnametarief_Digitale_meter_Normaal': 'TakeOutRate_DigitalMeter_Normal', 'Afnametarief_Digitale_meter_Exclusief_nacht': 'TakeOutRate_DigitalMeter_Excl_Night', 'Capaciteitstarief_Klassieke_meter': 'CapacityTariff_ClassicMeter', 'Afnametarief_Klassieke_meter_Normaal': 'TakeOutRate_ClassicMeter_Normal', 'Afnametarief_Klassieke_meter_Exclusief_nacht': 'TakeOutRate_ClassicMeter_Excl_Night', 'Prosumententarief': 'ProsumerRate', 'Tarief_databeheer_Jaar_en_maandgelezen_meters': 'YearlyAndMonthlyReadMeters', 'Tarief_databeheer_Kwartiergelezen_meters' : 'QuarterlyReadMeters'}, inplace=True)

    factDistributionCost['Van'] = pd.to_datetime(factDistributionCost['Van'], format='%d/%m/%Y')
    factDistributionCost['Tot'] = pd.to_datetime(factDistributionCost['Tot'], format='%d/%m/%Y')
    factDistributionCost['FromDateKey'] = factDistributionCost['Van'].dt.strftime('%Y%m%d').astype(int)
    factDistributionCost['ToDateKey'] = factDistributionCost['Tot'].dt.strftime('%Y%m%d').astype(int)
    factDistributionCost.drop(columns=['Van', 'Tot'], inplace=True)

    factDistributionCost['NetAdministratorID'] = factDistributionCost['Intercommunale'].map({
      'Fluvius Antwerpen': 'FLVAN',
      'Fluvius Limburg': 'FLVLI',
      'Fluvius West': 'FLVWE',
      'Gaselwest': 'GSLWE',
      'Imewo': 'IMWO',
      'Intergem': 'INTRG',
      'Iveka': 'IVKA',
      'Iverlek': 'IVRL',
      'PBE': 'PBE',
      'Sibelgas': 'SBLGS',
      'Fluvius (Antwerpen)': 'FLV(AN)',
      'Fluvius (Limburg)': 'FLV(LI)',
      'Fluvius (West)': 'FLV(WE)',
      'Fluvius (Imewo)': 'FLV(IMWO)',
      'Fluvius (Midden-Vlaanderen)': 'FLV(MVL)',
      'Fluvius (Kempen)': 'FLV(K)',
      'Fluvius (Zenne-Dijle)': 'FLV(ZD)',
      'Fluvius (Halle-Vilvoorde)': 'FLV(HV)',
    })
    dimNetAdministrator = pd.read_sql('SELECT NetAdministratorKey, NetAdministratorID FROM DimNetAdministrator', con=connection) 
    dimNetAdministrator['NetAdministratorID'] = dimNetAdministrator['NetAdministratorID'].str.strip() 
    factDistributionCost['NetAdministratorID'] = factDistributionCost['NetAdministratorID'].str.strip()
    factDistributionCost = factDistributionCost.merge(dimNetAdministrator, how='left', on='NetAdministratorID')
    factDistributionCost.drop(columns=['NetAdministratorID', 'Intercommunale'], inplace=True) 


    try:
        factDistributionCost.to_sql('FactDistributionCost', con=connection, if_exists='append', index=False) 
        print('FactDistributionCost created\n')
    except Exception:
        raise
    return

def readAndFillFactContribution(connection):
    print('Creating FactContribution table...')
    factContribution = pd.read_csv(f'{DATA_DIR}/input/Bijdragen.csv', sep=',')
    factContribution.rename(columns={'Energiebijdrage': 'Contribution', 'Federale_bijdrage_0_3000': 'FederalContribution_0_3000', 'Federale_bijdrage_3000_20000': 'FederalContribution_3000_20000', 'Federale_bijdrage_20000_50000': 'FederalContribution_20000_50000', 'Federale_bijdrage_50000_100000': 'FederalContribution_50000_100000', 'Bijdrage_energiefonds_residentiële_gebruiker': 'Contribution_EnergyFund_ResidentialUser', 'Bijdrage_energiefonds_niet_residentiële_gebruiker': 'Contribution_EnergyFund_NonResidentialUser'}, inplace=True)

    factContribution['Van'] = pd.to_datetime(factContribution['Van'], format='%d/%m/%Y')
    factContribution['Tot'] = pd.to_datetime(factContribution['Tot'], format='%d/%m/%Y')
    factContribution['FromDateKey'] = factContribution['Van'].dt.strftime('%Y%m%d').astype(int)
    factContribution['ToDateKey'] = factContribution['Tot'].dt.strftime('%Y%m%d').astype(int)
    factContribution.drop(columns=['Van', 'Tot'], inplace=True)

    try:
        factContribution.to_sql('FactContribution', con=connection, if_exists='append', index=False)
        print('FactContribution created\n')
    except Exception:
        raise
    return

def createAndFillDimContract(connection):
    print('Creating DimContract table...')
    contracts = pd.DataFrame(columns=['ContractName', 'ContractType'])
    contracts.loc[0] = ['DATS24 Elektriciteit', 'Variable']
    contracts.loc[1] = ['Eneco Zon & Wind Flex', 'Variable']
    contracts.loc[4] = ['OCTA+ Eco Clear', 'Variable']
    contracts.loc[5] = ['OCTA+ Fixed', 'Fixed']
    contracts.loc[6] = ['Bolt Elektriciteit', 'Variable']
    contracts['Leverancier'] = contracts['ContractName'].str.split(' ').str[0]

    try:
        contracts.to_sql('DimContract', con=connection, if_exists='append', index=False)
        print('DimContract created\n')
    except Exception:
        raise
    return

def readAndFillFactEnergyCost(connection):
    print('Creating FactEnergyCost table...')
    factEnergyCost = pd.read_csv(f'{DATA_DIR}/input/Energiekosten.csv', sep=';')
    factEnergyCost['ContractKey'] = factEnergyCost['ContractName'].map({
        'DATS24 Elektriciteit': 1,
        'Eneco Zon & Wind Flex': 2,
        'Octa+ Eco Clear': 3,
        'Octa+ Fixed': 4,
        'Bolt Elektriciteit': 5
    })
    factEnergyCost.drop(columns=['ContractName'], inplace=True)

    try:
        factEnergyCost.to_sql('FactEnergyCost', con=connection, if_exists='append', index=False)
        print('FactEnergyCost created\n')
    except Exception:
        raise
    return

if __name__ == '__main__':
    main()
