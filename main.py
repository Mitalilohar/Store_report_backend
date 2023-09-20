from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Response, BackgroundTasks
from fastapi.responses import FileResponse
import secrets
from fastapi import FastAPI
from pymongo import MongoClient
from config import Config
import pytz
import certifi
import asyncio
import csv
app = FastAPI()

# Set up the MongoDB connection
client = MongoClient(Config.MONGO_URI,tlsCAFile=certifi.where())
db = client.store


@app.post('/trigger_report', response_model=dict)
async def trigger_report(background_tasks: BackgroundTasks):
    try:
        report_id = secrets.token_urlsafe(16)
        background_tasks.add_task(generate_report, report_id)
        return {'report_id': report_id, 'message': 'Task initiated', 'status_code': 200}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Something went wrong: {str(e)}")


@app.get('/get_report', response_model=dict)
async def get_report(report_id: str = None):
    try:
        if not report_id:
            raise HTTPException(status_code=400, detail='Missing report ID')

        report_status = get_report_status_from_db(report_id)
        if not report_status:
            raise HTTPException(status_code=400, detail='Invalid report ID')

        if report_status == 'Running':
            return {'status': 'Running', 'message': 'Success', 'status_code': 200}
        elif report_status == 'Completed':
            report_data = generate_csv_from_data(report_id)
            if report_data:
                return FileResponse("report.csv",  filename="report.csv")
            else:
                raise HTTPException(
                    status_code=400, detail='Failed to retrieve report data')
        else:
            raise HTTPException(
                status_code=400, detail='Invalid report status')
    except Exception as e:
        print("error:- ", repr(e))
        raise HTTPException(
            status_code=500, detail=f"Something went wrong: {str(e)}")


async def generate_report(report_id):
    # Create a new report document in MongoDB
    report_doc = {
        'report_id': report_id,
        'status': 'Running',
        'started_at': datetime.utcnow()
    }
    db.reports.insert_one(report_doc)
    report_data = []
    stores_cursor = list(db.bq_results.find())[:10]

    store_tasks = []
    for store in stores_cursor:
        store_id = store['store_id']
        task = asyncio.create_task(
            calculate_uptime_downtime_extrapolate(store_id))
        store_tasks.append(task)

    # Wait for all tasks to complete
    report_data = await asyncio.gather(*store_tasks)

    updated_report_doc = {
        '$set': {
            'status': 'Completed',
            'completed_at': datetime.utcnow(),
            'data': report_data
        }
    }

    db.reports.find_one_and_update(
        {'report_id': report_id}, updated_report_doc)


def get_report_status_from_db(report_id):
    report = db.reports.find_one({'report_id': report_id})
    if report is None:
        return None
    else:
        return report['status']


def generate_csv_from_data(report_id):
    # Extract column names (keys of the dictionary)
    data = db.reports.find_one({'report_id': report_id})['data']
    column_names = data[0].keys() if data else []

    # Write data to a CSV file
    with open("report.csv", 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=column_names)

        # Write header
        writer.writeheader()

        # Write rows
        for row in data:
            writer.writerow(row)
    return True


async def calculate_uptime_downtime_extrapolate(store_id):
    # Filter data for the given store_id
    store_data = list(db.store_status.find({"store_id": store_id}))
    business_hours = list(db.menu_hours.find({"store_id": store_id}))
    timezone_info = db.bq_results.find_one({"store_id": store_id})

    # Extract relevant data from MongoDB documents
    timestamps = [item["timestamp_utc"] for item in store_data]
    statuses = [item["status"] for item in store_data]
    start_time_local = [item["start_time_local"] for item in business_hours]
    end_time_local = [item["end_time_local"] for item in business_hours]

    # Convert timestamps to datetime objects and apply the timezone
    timezone_store = pytz.timezone(timezone_info["timezone_str"])
    timestamps = [timezone_store.localize(datetime.strptime(
        ts, "%Y-%m-%d %H:%M:%S.%f UTC")) for ts in timestamps]

    # Convert start_time_local and end_time_local to datetime objects
    start_times = [datetime.strptime(start, "%H:%M:%S")
                   for start in start_time_local]
    end_times = [datetime.strptime(end, "%H:%M:%S") for end in end_time_local]

    # Initialize dictionaries to store calculated uptime and downtime
    uptime_last_hour = downtime_last_hour = 0
    uptime_last_day = downtime_last_day = 0
    uptime_last_week = downtime_last_week = 0

    # Rest of the function should use statuses for calculating uptime and downtime
    # print(business_hours,len(business_hours))
    for i in range(len(business_hours)):
        start = timezone_store.localize(start_times[i])
        end = timezone_store.localize(end_times[i])

        # Filter data within the current business hour
        relevant_data = [statuses[j] for j in range(
            len(timestamps)) if start.time() <= timestamps[j].time() <= end.time()]

        if not relevant_data:
            continue

        # Calculate duration of the current business hour
        hour_duration = (end - start).total_seconds() / 3600  # in hours

        # Calculate uptime and downtime for the current business hour
        uptime = relevant_data.count(
            'active') * 60 / len(relevant_data)  # in minutes
        downtime = relevant_data.count(
            'inactive') * 60 / len(relevant_data)  # in minutes

        # Update cumulative uptime and downtime
        uptime_last_hour += uptime
        downtime_last_hour += downtime

        # Extrapolate to the entire day
        uptime_last_day += (uptime / hour_duration) * 24  # in hours
        downtime_last_day += (downtime / hour_duration) * 24  # in hours

        # Extrapolate to the entire week
        uptime_last_week += (uptime / hour_duration) * 24 * 7  # in hours
        downtime_last_week += (downtime / hour_duration) * 24 * 7  # in hours

    # Round the values to 2 decimal places
    uptime_last_hour = round(uptime_last_hour, 2)
    downtime_last_hour = round(downtime_last_hour, 2)
    uptime_last_day = round(uptime_last_day, 2)
    downtime_last_day = round(downtime_last_day, 2)
    uptime_last_week = round(uptime_last_week, 2)
    downtime_last_week = round(downtime_last_week, 2)
    return {
        "store_id": store_id,
        "uptime_last_hour": uptime_last_hour,
        "downtime_last_hour": downtime_last_hour,
        "uptime_last_day": uptime_last_day,
        "downtime_last_day": downtime_last_day,
        "uptime_last_week": uptime_last_week,
        "downtime_last_week": downtime_last_week
    }
