IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'DigitalMeterDWH')
BEGIN
  CREATE DATABASE DigitalMeterDWH;
END;
GO

USE [DigitalMeterDWH]

CREATE TABLE [dbo].[DimDate](
  [DateKey] [int] NOT NULL PRIMARY KEY,
  [FullDateAlternateKey] [date] NOT NULL,
  [DayOfMonth] [varchar](2) NOT NULL,
  [NameDayOfWeekEN] [varchar](10) NOT NULL,
  [NameDayOfWeekDutch] [varchar](10) NOT NULL,
  [DayOfWeek] [char](1) NOT NULL,
  [DayOfWeekInMonth] [varchar](2) NOT NULL,
  [DayOfWeekInYear] [varchar](2) NOT NULL,
  [DayOfQuarter] [varchar](3) NOT NULL,
  [DayOfYear] [varchar](3) NOT NULL,
  [WeekOfMonth] [varchar](1) NOT NULL,
  [WeekOfQuarter] [varchar](2) NOT NULL,
  [WeekOfYear] [varchar](2) NOT NULL,
  [Month] [varchar](2) NOT NULL,
  [NameMonthEN] [varchar](10) NOT NULL,
  [NameMonthDutch] [varchar](10) NOT NULL,
  [MonthOfQuarter] [varchar](2) NOT NULL,
  [Quarter] [char](1) NOT NULL,
  [QuarterName] [varchar](9) NOT NULL,
  [Year] [char](4) NOT NULL,
  [MonthYear] [varchar](10) NOT NULL,
  [MMYYYY] [varchar](6) NOT NULL
)

CREATE TABLE [dbo].[DimTime](
  [TimeKey] INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  [FullTime] [varchar](8) NOT NULL,
  [Hour] [varchar](2) NOT NULL,
  [Minute] [varchar](2) NOT NULL,
  [Second] [varchar](2) NOT NULL,
  [AMPM] [varchar](8) NOT NULL
)

CREATE TABLE [dbo].[DimWeatherStation](
  [WeatherStationKey] INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  [WeatherStationID] [nchar](5) NOT NULL,
  [WeatherStationName] [nvarchar](40) NULL,
  [Latitude] [decimal](9, 6) NULL,
  [Longitude] [decimal](9, 6) NULL,
  [Altitude] [decimal](9, 6) NULL
)

CREATE TABLE [dbo].[DimNetAdministrator](
  [NetAdministratorKey] INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  [NetAdministratorID] [nchar](9) NOT NULL,
  [NetAdministratorName] [nvarchar](40) NULL
)

CREATE TABLE [dbo].[DimUser](
  [UserKey] INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  [EAN_ID] [int] NOT NULL,
  [ContractType] [nvarchar](40) NULL,
  [HeatPumpIndicator] [char](1) NULL,
  [ElectricVehicleIndicator] [char](1) NULL,
  [PVInstallationIndicator] [char](1) NULL
)

CREATE TABLE [dbo].[FactWeather](
  [WeatherKey]  INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  [DateKey] [int] NOT NULL,
  [TimeKey] [int] NOT NULL,
  [WeatherStationKey] [int] NOT NULL,
  [PrecipQuantity] [float] NULL,
  [TempAvg] [float] NULL,
  [TempMax] [float] NULL,
  [TempMin] [float] NULL,
  [TempGrassPt100Avg] [float] NULL,
  [TempSoilAvg] [float] NULL,
  [TempSoilAvg5cm] [float] NULL,
  [TempSoilAvg10cm] [float] NULL,
  [TempSoilAvg20cm] [float] NULL,
  [TempSoilAvg50cm] [float] NULL,
  [WindSpeed10m] [float] NULL,
  [WindSpeedAvg30m] [float] NULL,
  [WindGustsSpeed] [float] NULL,
  [HumidityRelShelterAvg] [float] NULL,
  [Pressure] [float] NULL,
  [SunDuration] [float] NULL,
  [ShortWaveFromSkyAvg] [float] NULL,
  [SunIntAvg] [float] NULL,
)

CREATE TABLE [dbo].[FactBelpex](
  [DateKey] [int] NOT NULL,
  [TimeKey] [int] NOT NULL,
  [BelpexPrice] [decimal](9, 6) NULL,
  [Belpex_RLP_MPrice] [decimal](9, 6) NULL,
  PRIMARY KEY ([DateKey], [TimeKey])
)

CREATE TABLE [dbo].[FactEnergyUsage](
  [DateKey] [int] NOT NULL,
  [TimeKey] [int] NOT NULL,
  [UserKey] [int] NOT NULL,
  [Usage_kWh] [decimal](9, 6) NULL,
  [Injection_kWh] [decimal](9, 6) NULL,
  [MonthlyPeak_kW] [decimal](9, 6) NULL,
  [DaytimeRate] [char](1) NULL,
  PRIMARY KEY ([DateKey], [TimeKey], [UserKey])
)

CREATE TABLE [dbo].[FactDistributionCost](
  [DistributionCostKey] INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  [FromDateKey] [int] NOT NULL,
  [ToDateKey] [int] NOT NULL,
  [NetAdministratorKey] [int] NOT NULL,
  [CapacityTariff_DigitalMeter] [decimal](9, 6) NULL,
  [TakeOutRate_DigitalMeter_Normal] [decimal](9, 6) NULL,
  [TakeOutRate_DigitalMeter_Excl_Night] [decimal](9, 6) NULL,
  [CapacityTariff_ClassicMeter] [decimal](9, 6) NULL,
  [TakeOutRate_ClassicMeter_Normal] [decimal](9, 6) NULL,
  [TakeOutRate_ClassicMeter_Excl_Night] [decimal](9, 6) NULL,
  [ProsumerRate] [decimal](9, 6) NULL,
  [YearlyAndMonthlyReadMeters] [decimal](9, 6) NULL,
  [QuarterlyReadMeters] [decimal](9, 6) NULL,
)

CREATE TABLE [dbo].[FactContribution](
  [ContributionKey] INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  [FromDateKey] [int] NOT NULL,
  [ToDateKey] [int] NOT NULL,
  [Contribution] [decimal](9, 6) NULL,
  [FederalContribution_0_3000] [decimal](9, 6) NULL,
  [FederalContribution_3000_20000] [decimal](9, 6) NULL,
  [FederalContribution_20000_50000] [decimal](9, 6) NULL,
  [FederalContribution_50000_100000] [decimal](9, 6) NULL,
  [Contribution_EnergyFund_ResidentialUser] [decimal](9, 6) NULL,
  [Contribution_EnergyFund_NonResidentialUser] [decimal](9, 6) NULL,
)

CREATE TABLE [dbo].[DimContract](
  [ContractKey] INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  [ContractName] [nvarchar](40) NULL,
  [ContractType] [nvarchar](40) NULL,
  [Leverancier] [nvarchar](40) NULL,
)

CREATE TABLE [dbo].[FactEnergyCost](
  [EnergyCostKey] INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  [DateKey] [int] NOT NULL,
  [ContractKey] [int] NOT NULL,
  [SingleMeterFixed] [decimal](20, 9) NULL,
  [DualMeterDayFixed] [decimal](20, 9) NULL,
  [DualMeterNightFixed] [decimal](20, 9) NULL,
  [ExclusiveNightMeterFixed] [decimal](20, 9) NULL,
  [SingleMeterVariableMeterFactor] [decimal](20, 9) NULL,
  [SingleMeterVariableBalancingCost] [decimal](20, 9) NULL,
  [DualMeterDayVariableMeterFactor] [decimal](20, 9) NULL,
  [DualMeterDayVariableBalancingCost] [decimal](20, 9) NULL,
  [DualMeterNightVariableMeterFactor] [decimal](20, 9) NULL,
  [DualMeterNightVariableBalancingCost] [decimal](20, 9) NULL,
  [ExclusiveNightMeterVariableMeterFactor] [decimal](20, 9) NULL,
  [ExclusiveNightMeterVariableBalancingCost] [decimal](20, 9) NULL,
  [DynamicMeterCost] [decimal](20, 9) NULL,
  [DynamicBalancingCost] [decimal](20, 9) NULL,
  [SingleMeterInjectionMeterFactor] [decimal](20, 9) NULL,
  [SingleMeterInjectionBalancingCost] [decimal](20, 9) NULL,
  [DualMeterDayInjectionMeterFactor] [decimal](20, 9) NULL,
  [DualMeterDayInjectionBalancingCost] [decimal](20, 9) NULL,
  [DualMeterNightInjectionMeterFactor] [decimal](20, 9) NULL,
  [DualMeterNightInjectionBalancingCost] [decimal](20, 9) NULL,
  [DynamicMeterInjectionMeterFactor] [decimal](20, 9) NULL,
  [DynamicMeterInjectionBalancingCost] [decimal](20, 9) NULL,
  [AdministrativeCosts] [decimal](20, 9) NULL,
  [GreenElectricity] [decimal](20, 9) NULL,
  [WKK] [decimal](20, 9) NULL,
)

ALTER TABLE [dbo].[FactWeather] ADD CONSTRAINT [FK_FactWeather_DimDate] FOREIGN KEY ([DateKey]) REFERENCES [dbo].[DimDate] ([DateKey])
ALTER TABLE [dbo].[FactWeather] ADD CONSTRAINT [FK_FactWeather_DimTime] FOREIGN KEY ([TimeKey]) REFERENCES [dbo].[DimTime] ([TimeKey])
ALTER TABLE [dbo].[FactWeather] ADD CONSTRAINT [FK_FactWeather_DimWeatherStation] FOREIGN KEY ([WeatherStationKey]) REFERENCES [dbo].[DimWeatherStation] ([WeatherStationKey])

ALTER TABLE [dbo].[FactBelpex] ADD CONSTRAINT [FK_FactBelpex_DimDate] FOREIGN KEY ([DateKey]) REFERENCES [dbo].[DimDate] ([DateKey])
ALTER TABLE [dbo].[FactBelpex] ADD CONSTRAINT [FK_FactBelpex_DimTime] FOREIGN KEY ([TimeKey]) REFERENCES [dbo].[DimTime] ([TimeKey])

ALTER TABLE [dbo].[FactEnergyUsage] ADD CONSTRAINT [FK_FactEnergyUsage_DimDate] FOREIGN KEY ([DateKey]) REFERENCES [dbo].[DimDate] ([DateKey])
ALTER TABLE [dbo].[FactEnergyUsage] ADD CONSTRAINT [FK_FactEnergyUsage_DimTime] FOREIGN KEY ([TimeKey]) REFERENCES [dbo].[DimTime] ([TimeKey])
ALTER TABLE [dbo].[FactEnergyUsage] ADD CONSTRAINT [FK_FactEnergyUsage_DimUser] FOREIGN KEY ([UserKey]) REFERENCES [dbo].[DimUser] ([UserKey])

ALTER TABLE [dbo].[FactDistributionCost] ADD CONSTRAINT [FK_FactDistributionCost_DimDate_From] FOREIGN KEY ([FromDateKey]) REFERENCES [dbo].[DimDate] ([DateKey])
ALTER TABLE [dbo].[FactDistributionCost] ADD CONSTRAINT [FK_FactDistributionCost_DimDate_To] FOREIGN KEY ([ToDateKey]) REFERENCES [dbo].[DimDate] ([DateKey])
ALTER TABLE [dbo].[FactDistributionCost] ADD CONSTRAINT [FK_FactDistributionCost_DimNetAdministrator] FOREIGN KEY ([NetAdministratorKey]) REFERENCES [dbo].[DimNetAdministrator] ([NetAdministratorKey])

ALTER TABLE [dbo].[FactContribution] ADD CONSTRAINT [FK_FactContribution_DimDate_From] FOREIGN KEY ([FromDateKey]) REFERENCES [dbo].[DimDate] ([DateKey])
ALTER TABLE [dbo].[FactContribution] ADD CONSTRAINT [FK_FactContribution_DimDate_To] FOREIGN KEY ([ToDateKey]) REFERENCES [dbo].[DimDate] ([DateKey])

ALTER TABLE [dbo].[FactEnergyCost] ADD CONSTRAINT [FK_FactEnergyCost_DimDate] FOREIGN KEY ([DateKey]) REFERENCES [dbo].[DimDate] ([DateKey])
ALTER TABLE [dbo].[FactEnergyCost] ADD CONSTRAINT [FK_FactEnergyCost_DimContract] FOREIGN KEY ([ContractKey]) REFERENCES [dbo].[DimContract] ([ContractKey])