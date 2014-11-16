#!/usr/bin/env python

# This script uses the boto, the Python interface to Amazon Web Services - http://boto.readthedocs.org/
#
# Requirements:
#   Install onto EC2 instance that has the AWS cli installed - http://aws.amazon.com/cli/
#   AWS IAM user with permission to read from CloudWatch including access key ID and secret access key
#   Write privileges if pushing Linux metrics to CloudWatch
#   Sumo Logic installed collector on instance running the script, or a hosted collector
#
# Both the default EC2 metrics and custom Linux metrics are pulled by this script.
# The default metrics are automatically pushed every 5 minutes
# The Linux metrics can be pushed to CloudWatch using the Linux Monitoring Scripts - http://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/mon-scripts-perl.html
#
# Cloudwatch results can be pushed to Sumo using either an installed collector or a hosted collector. 
# For an installed collector use the write_to_file function
# For a hosted collector use the push_to_collector function

import boto, datetime, json, urllib2, time
from boto import ec2
from pytz import timezone
import boto.ec2.cloudwatch
from time import gmtime, strftime

# Set our AWS access keys. Must have Cloudwatch permissions in AWS IAM 
AWS_ACCESS_KEY_ID = 'PUT YOUR ACCESS KEY HERE'
AWS_SECRET_ACCESS_KEY = 'PUT YOUR SECRET ACCESS KEY HERE'

### Set Global Variables ###

# The Sumo Logic collector where we are sending logs
url = 'https://collectors.sumologic.com/receiver/v1/http/ZaVnC4dhaV2QuDheBqJVYAR26vsjG4CwB1CNpUQwJJ8OWLd8wB1bOCX4BYrYiYah7oL_hqQCB-R-X0e0QdIMSQM3JuBuWNr856CiFZRO-0gsY1CIzOit2g=='

# The file where we are writing our logs
boto_log = '/home/ubuntu/log/boto.log'

### Set AWS EC2 Variables ###
# The AWS regions from which we are collecting log data
regions = ["us-east-1", "us-west-1", "us-west-2", "ap-northeast-1", "ap-southeast-1", "ap-southeast-2", "eu-west-1", "sa-east-1"]

### Set AWS CloudWatch Variables ###
# Start and end times for the Cloudwatch query
query_end_time = datetime.datetime.utcnow()
query_start_time = query_end_time - datetime.timedelta(minutes=9)

# Set the default EC2 metrics we want to pull
# These are sent by default to CloudWatch

ec2_metrics = [ 'CPUCreditUsage', 'CPUCreditBalance', 'CPUUtilization', 'NetworkIn', 'NetworkOut', 'DiskReadBytes', 'DiskReadOps', 'DiskWriteBytes', 'DiskWriteOps', 'StatusCheckFailed', 'StatusCheckFailed_Instance', 'StatusCheckFailed_System' ]

# Set the Linux EC2 metrics we want to pull
# Requires that Linux metrics be pushed to Cloudwatch using the Linux Monitoring scripts
# http://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/mon-scripts-perl.html

linux_metrics = [ 'DiskSpaceUtilization', 'MemoryUtilization', 'SwapUtilization' ]

### CONSTANTS ###
# Generate UTC timestamps - create a timestamp for local logging
timeStamp = strftime("%Y-%m-%d %H:%M:%S", gmtime())
timeStamp += "Z"

# Create the dictionary where we will store our results
d = {}

### Functions ###

## Writes a given log message to file with timestamp. 
def write_to_file(log_data):
    my_file = open(boto_log, "a")
    my_file.write(timeStamp + ': ' + log_data + '\n')
    my_file.close()

## Pushes a given log message with timestamp to a hosted collector.
def push_to_collector(log_data):
    log_data = timeStamp + ': ' + log_data + '\n'
    print urllib2.urlopen(url, log_data).read()

## Convert the timestamp returned from CloudWatch to a human readable format.
def cloudwatch_timestamp_to_utc(timestamp):
    l = timestamp.split(' ')
    ts = l[0] + 'T' + l[1] + 'Z'
    return ts

## Pull instance metrics from CloudWatch.
def get_cloudwatch_metrics(namespace, metric, unit):
    #data_points = c.get_metric_statistics(300, query_start_time, query_end_time, metric,'AWS/EC2', 'Average', dimensions={'InstanceId' : d["InstanceId"]}, unit=unit) 
    data_points = c.get_metric_statistics(300, query_start_time, query_end_time, metric, namespace, 'Average', dimensions={'InstanceId' : d["InstanceId"]}, unit=unit) 

    # Check to see if any metrics are returned
    if data_points:

        # Data is returned from CloudWatch in a list of dictionaries. Based on our query (look back 9 minutes for a 5 minute interval) 
        # the assumption is being made that only one result is being returned. 
        data_point = data_points[0]

        # Extract Timestamp, pass it to cloudwatch_timestamp_to_utc for processing.
        # Timestamp is returned as a tuple, we need to make it pretty for human consumption
        timestamp = cloudwatch_timestamp_to_utc(str(data_point['Timestamp']))

        # Update the computer friendly timestamp with a human friendly one
        data_point['Timestamp'] = timestamp

        # Write our results back into a list
        l = [data_point]

    else:
        # If there are no results for this metric, the list is empty 
        l = []
    
    # Add the metric to our log message
    d[metric] = l 


# Iterate through each of the regions
for region in regions:
    ec2_conn = ec2.connect_to_region(region, aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
    reservations = ec2_conn.get_all_instances()
    instances = [i for r in reservations for i in r.instances]

    for i in instances:
    
        # Set the region
        d['region'] = region

        # Extract attributes
        d['availability_zone'] = i.placement
        d['InstanceId'] = i.id
        d['state'] = i.state
        d['state_code'] = i.state_code

        # Extract customer name or other unique tag
        # Mostly applicable in a multi-tenant environment
        #if 'customerName' in i.tags:
        #    d['customerName'] = i.tags['customerName']

        if i.state == 'running':
            d['state_reason'] = i.state_reason
            d['public_dns_name'] = i.public_dns_name

        else:
            d["state_reason"] = i.state_reason['code']
            d["state_reason_msg"] = i.state_reason['message']
            
        # Create a connection to CloudWatch
        c = boto.ec2.cloudwatch.connect_to_region(region, aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
        
        # Iterate through each of the metrics in ec2_metrics
        for metric in ec2_metrics:
            namespace = 'AWS/EC2'
            if metric == 'CPUUtilization':
                get_cloudwatch_metrics(namespace, metric, 'Percent')
            
            elif ( metric == 'NetworkIn' or metric == 'NetworkOut' or metric == 'DiskReadBytes' or metric == 'DiskWriteBytes'):
                get_cloudwatch_metrics(namespace, metric, 'Bytes/Second')
            
            elif (metric == 'DiskReadOps' or metric == 'DiskWriteOps'):
                get_cloudwatch_metrics(namespace, metric, 'Count/Second')

            else:
                get_cloudwatch_metrics(namespace, metric, 'Count')

        # Iterate through each of the metrics in linux_metrics
        for metric in linux_metrics:
            namespace = 'System/Linux'
            get_cloudwatch_metrics(namespace, metric, 'Count')

    jsonResults = json.dumps(d)

    # Uncomment to display results to the screen
    print jsonResults

# Uncomment the appropriate function for your environment.
#    write_to_file(jsonResults)
#    push_to_collector(jsonResults)          
