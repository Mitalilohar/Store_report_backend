# Restaurant Monitoring System

The Restaurant Monitoring System is a backend API that helps restaurant
owners track the online and offline status of their stores during
business hours. The system polls each store roughly every hour and
records whether the store was active or not in a CSV file. The system
also has data on the business hours of all the stores and the timezone
for each store.

The system provides two APIs:

1.  /trigger_report endpoint that triggers the generation of a report
    from the data provided (stored in the database). The API has no
    input and returns a report ID (a random string). The report ID is
    used to poll the status of report completion.

2.  /get_report endpoint that returns the status of the report or the
    CSV. The API takes a report ID as input and returns the following:

    -   If report generation is not complete, return "Running" as the
        output
    -   If report generation is complete, return "Complete" along with
        the CSV file with the following schema: store_id,
        uptime_last_hour(in minutes), uptime_last_day(in hours),
        update_last_week(in hours), downtime_last_hour(in minutes),
        downtime_last_day(in hours), downtime_last_week(in hours) The
        uptime and downtime reported in the CSV only include
        observations within business hours. The system extrapolates
        uptime and downtime based on the periodic polls we have ingested
        to the entire time interval.

## Data Sources 

The system has the following three sources of data:

1.  A CSV file with three columns (store_id, timestamp_utc, status)
    where status is active or inactive. All timestamps are in UTC.

2.  A CSV file with data on the business hours of all the stores. The
    schema of this data is store_id, dayOfWeek(0=Monday, 6=Sunday),
    start_time_local, end_time_local. These times are in the local time
    zone. If data is missing for a store, assume it is open 24\*7.

3.  A CSV file with data on the timezone for each store. The schema is
    store_id, timezone_str. If data is missing for a store, assume it is
    America/Chicago. This is used so that data sources 1 and 2 can be
    compared against each other.
    


