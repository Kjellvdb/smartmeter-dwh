CREATE OR ALTER PROCEDURE getTotalUsageAndInjection @EANID int, @YYYYMM varchar(6)
AS
BEGIN

	DECLARE @MM varchar(2), @YYYY varchar(4), @MMYYYY varchar(6)
	SET @MM = SUBSTRING(@YYYYMM, 5, 7)
	SET @YYYY = SUBSTRING(@YYYYMM, 0, 5)
	SET @MMYYYY = @MM + @YYYY

	SELECT SUM(Usage_kWh) AS 'TotalUsage', SUM(Injection_kWh) AS 'TotalInjection' 
	FROM DigitalMeterDWH.dbo.FactEnergyUsage feu 
	JOIN DigitalMeterDWH.dbo.DimUser du ON feu.UserKey = du.UserKey 
	JOIN DigitalMeterDWH.dbo.DimDate dd ON feu.DateKey = dd.DateKey 
	WHERE du.EAN_ID = @EANID AND dd.MMYYYY = @MMYYYY

END;

CREATE OR ALTER PROCEDURE getAverageHoursSunPerDay @WeatherStationID int
AS
BEGIN

	DECLARE @LastMonth Date, @LastMonthKey int
	SET @LastMonth = DATEADD(DAY, -31, GETDATE())
	SET @LastMonthKey = FORMAT(@LastMonth, 'yyyyMMdd')
	
	SELECT AVG(SunDuration) / 60 AS 'AverageHoursSunPerDay'
	FROM DigitalMeterDWH.dbo.FactWeather fw
	JOIN DigitalMeterDWH.dbo.DimWeatherStation dws ON fw.WeatherStationKey = dws.WeatherStationKey
	WHERE dws.WeatherStationID = @WeatherStationID AND DateKey > @LastMonthKey

END;

CREATE OR ALTER PROCEDURE updateBelpexValue @BelpexValue decimal(9, 6), @BelpexType varchar(20), @DateKey int, @FullTime varchar(8)
AS
BEGIN

	DECLARE @TimeKey int
	SET @TimeKey = (SELECT TimeKey FROM DigitalMeterDWH.dbo.DimTime WHERE FullTime = @FullTime)
	IF @BelpexType = 'BelpexPrice'
	BEGIN
				
		UPDATE DigitalMeterDWH.dbo.FactBelpex
				SET BelpexPrice = @BelpexValue
				WHERE DateKey = @DateKey AND TimeKey = @TimeKey

	END

	ELSE IF @BelpexType = 'Belpex_RLP_MPrice'
		BEGIN

				UPDATE DigitalMeterDWH.dbo.FactBelpex
				SET Belpex_RLP_MPrice = @BelpexValue
				WHERE DateKey = @DateKey AND TimeKey = @TimeKey
		
	END

END;