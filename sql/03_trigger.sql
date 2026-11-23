CREATE OR ALTER TRIGGER UpdateFactBelpex
ON DigitalMeterDWH.dbo.FactBelpex
AFTER INSERT, UPDATE
AS
BEGIN
    IF TRIGGER_NESTLEVEL() > 1 
        RETURN;

    IF UPDATE(Belpex_RLP_MPrice) 
        RETURN;

    WITH TargetMonths AS (
        SELECT DISTINCT d.Year * 100 + d.Month AS YearMonth
        FROM inserted i
        JOIN DigitalMeterDWH.dbo.DimDate d ON i.DateKey = d.DateKey

        UNION

        SELECT DISTINCT dd_null.Year * 100 + dd_null.Month AS YearMonth
        FROM DigitalMeterDWH.dbo.FactBelpex fb_null
        JOIN DigitalMeterDWH.dbo.DimDate dd_null ON fb_null.DateKey = dd_null.DateKey
        WHERE fb_null.Belpex_RLP_MPrice IS NULL
    ), AvgBelpexPerMonth AS (
        SELECT dd.Year, dd.Month, AVG(fb.BelpexPrice) AS AvgBelpexPrice
        FROM DigitalMeterDWH.dbo.FactBelpex fb
        JOIN DigitalMeterDWH.dbo.DimDate dd ON fb.DateKey = dd.DateKey
        WHERE (dd.Year * 100 + dd.Month) IN (SELECT YearMonth FROM TargetMonths)
        GROUP BY dd.Year, dd.Month
    )
    UPDATE fb
    SET fb.Belpex_RLP_MPrice = abpm.AvgBelpexPrice
    FROM DigitalMeterDWH.dbo.FactBelpex fb
    JOIN DigitalMeterDWH.dbo.DimDate dd ON fb.DateKey = dd.DateKey
    JOIN AvgBelpexPerMonth abpm ON dd.Year = abpm.Year AND dd.Month = abpm.Month;

END;
GO

UPDATE DigitalMeterDWH.dbo.FactBelpex
SET BelpexPrice = BelpexPrice;
GO