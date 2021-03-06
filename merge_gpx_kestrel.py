"""
Add locations from gpx files to observations in Kestrel weather data files

Usage
    python3 merge_kestrel_gpx.py [directory]

Details
    This script adds latitude and longitude from a gpx file to the weather
observations in a csv file exported from Kestrel Link. It matches files based on
name and matches locations from the gpx file to observations in the csv file
based on time. Where no location is perfectly coincident with an observation it
uses linear interpolation between the previous and subsequent locations. The
merged data is written to a new 'located_data' subdirectory and processed original
files are moved to a new 'original_data' subdirectory.

Caveats
    * Corresponding files must have the same name (e.g. foo.gpx and foo.csv)
    * Assumes times in the Kestrel weather data are CET (central European Time)
"""

import os
from sys import argv
import csv
from datetime import datetime

import gpxpy
import pytz

# Determine the target directory from the specified paths
def get_target_dir(paths):
    args = argv[1:]

    # If no path specified, use the current directory
    if len(args) == 0:
        return os.getcwd()

    # If one path, confirm it is a file or directory
    elif len(args) == 1:
        path = os.path.abspath(args[0])

        # If the path is an existing directory, use it
        if os.path.isdir(path):
            return path

        # If the path is a file, use its directory
        elif os.path.isfile(path):
            return os.path.dirname(path)

        # Fail if the path does not exist
        else:
            print('No such directory: ' + path)

    # Fail if more than one path was specified
    else:
        print('Please specify a single directory (blank for current dir)')
        print('  got: {0}'.format(args))


# Find all gpx files in the target directory
def get_gpx_files(target_dir):
    gpx_files = []
    for f in os.listdir(target_dir):
        if os.path.splitext(f)[1] == '.gpx':
            gpx_files.append(os.path.join(target_dir, f))
    return gpx_files


# Ensure the target directory contains 'original_data' and 'located_data' subdirectories
def setup_dirs(target_dir):
    originals_dir = os.path.join(target_dir, 'original_data')
    if not os.path.isdir(originals_dir):
        os.mkdir(originals_dir)

    located_dir = os.path.join(target_dir, 'located_data')
    if not os.path.isdir(located_dir):
        os.mkdir(located_dir)

    return originals_dir, located_dir


# Find the kestrel data file corresponding to the gpx file
def get_kestrel_file(gpx_file):
    # Assume the kestrel file is a csv with the same name as the gpx file
    return os.path.splitext(gpx_file)[0] + '.csv'


# Merge the gpx and kestrel data files
def merge_gpx_kestrel(gpx_path, kestrel_path, located_path):
    # Load all points in the gpx file
    with open(gpx_path, 'r') as gpx_file:
        gpx = gpxpy.parse(gpx_file)
        points = []
        for point_data in gpx.get_points_data():
            point = point_data.point
            point.time = pytz.utc.localize(point.time)
            points.append(point)

    with open(located_path, 'w') as located_file:
        with open(kestrel_path, 'r') as kestrel_file:
            # Write the preface rows unchanged
            for i in range(9):
                located_file.write(next(kestrel_file))

            # Read and clean the data headers from the kestrel file
            kestrel_reader = csv.DictReader(kestrel_file)
            while kestrel_reader.fieldnames[-1] == '':
                kestrel_reader.fieldnames.pop()

            # Add location headers and write to the located file
            headers = kestrel_reader.fieldnames + ['latitude', 'longitude', 'elevation']
            located_writer = csv.DictWriter(located_file, fieldnames=headers)
            located_writer.writeheader()

            # Write the units row unchanged
            located_file.write(next(kestrel_file))

            # Merge the gpx and kestrel files
            for row in kestrel_reader:
                # Parse the kestrel 'Time' field, assuming times are CET
                kestrel_time = datetime.strptime(row['Time'], '%Y-%m-%d %H:%M:%S')
                kestrel_time = pytz.timezone('CET').localize(kestrel_time)

                # Find first gpx point after the kestrel measurement
                for i, point in enumerate(points):
                    if point.time > kestrel_time:
                        after_point = point
                        break

                # i == 0 means no gpx point before measurement so location
                # cannot be interpolated
                if i != 0:
                    # Find the point prior to the after point
                    before_point = points[i-1]

                    if before_point.time == kestrel_time:
                        row.update({ 'latitude': before_point.latitude })
                        row.update({ 'longitude': before_point.longitude })
                        row.update({ 'elevation': before_point.elevation })
                    else:
                        seconds = (after_point.time - before_point.time).seconds * 1.0

                        # Seconds == 0 means no gpx point after measurement so
                        # location cannot be interpolated
                        if seconds != 0:
                            latitude_rate = (after_point.latitude - before_point.latitude) / seconds
                            longitude_rate = (after_point.longitude - before_point.longitude) / seconds
                            elevation_rate = (after_point.elevation - before_point.elevation) / seconds

                            elapsed = (kestrel_time - before_point.time).seconds * 1.0
                            row.update({ 'latitude': before_point.latitude + (elapsed * latitude_rate) })
                            row.update({ 'longitude': before_point.longitude + (elapsed * longitude_rate) })
                            row.update({ 'elevation': before_point.elevation + (elapsed * elevation_rate) })

                # Write the located data
                located_writer.writerow(row)


def run(paths):
    # Determine the target directory from the specified paths
    target_dir = get_target_dir(paths)

    # Find all gpx files in the target dir
    gpx_files = get_gpx_files(target_dir)

    print('Combining files in ' + target_dir)
    if not gpx_files:
        print('  No gpx files')
    else:
        for gpx_file in gpx_files:
            gpx_filename = os.path.basename(gpx_file)

            # Check for a matching kestrel file
            kestrel_file = get_kestrel_file(gpx_file)
            if not os.path.isfile(kestrel_file):
                print('  ' + gpx_filename + ' - No matching kestrel file - skipping')
            else:
                # Set up subdirectories for original and located files
                originals_dir, located_dir = setup_dirs(target_dir)

                # Build a path for the located file
                kestrel_filename = os.path.basename(kestrel_file)
                name, ext = os.path.splitext(kestrel_filename)
                located_filename = name + '-located' + ext
                located_file = os.path.join(located_dir, located_filename)

                # Merge the gpx and kestrel data files in the 'located_data' directory
                merge_gpx_kestrel(gpx_file, kestrel_file, located_file)
                print('  ' + gpx_filename + ' + ' + kestrel_filename + ' -> ' + located_filename)

                # Move the original gpx and kestrel files to the 'originals' directory
                os.rename(gpx_file, os.path.join(originals_dir, gpx_filename))
                os.rename(kestrel_file, os.path.join(originals_dir, kestrel_filename))
                spacer = ' ' * (len(gpx_filename) + len(kestrel_filename) + 5)
                print(spacer + ' -> ', end='')
                print(os.path.join(os.path.basename(originals_dir), gpx_filename), end='')
                print(' + ', end='')
                print(os.path.join(os.path.basename(originals_dir), kestrel_filename))


if __name__ == "__main__":
    run(argv[1:])
