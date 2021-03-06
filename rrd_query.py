#!/usr/bin/env /usr/local/bin/python2.7

# rrd_query.py - Put together complex rrd queries
# Written by Patrick Scott Gavin 2013

# This code was put together for a very specific nagios installation
# It is not meant for general release and I cannot guarantee or support
# it.

# I put this together because I was having problems getting the python rrd module working

import sys
sys.path.append('/usr/local/lib/python2.7/site-packages/')
import rrdtool
import xml.etree.ElementTree as ET
import re
import subprocess

cf_dict = {'avg':'AVERAGE','min':'MINIMUM','max':'MAXIMUM'}

class RRDQueryError (Exception):
    '''
    Standard class exception.
    '''
    pass

class RRDQuery:
    '''
    RRDQuery is meant to provide an interface for putting together complex or repetitive rrd queries.
    It currently relies on pnp4nagios xml files for some of the work, but may not in the future.
    Data structures maintained include:
    file_path -     A path to the rrdfile
    start_time -    The start time for the rrd query
    end_time -      The end time for the rrd query
    command_list -  A list of rrd commands that make up the query
    '''
    
    def count_datastores(self):
        '''
        ds_count takes an info dictionary (created by rrdtool.info) and
        returns the number of datastores in the rrd file.
        '''
        
        index = 1
        
        while "ds[{}].type".format(index) in self.rrd_info.keys():
            index += 1
            
        return index
    
    def build_label_dict(self):
        '''
        buildDict will create a dict that maps the datastore value to the name or label
        using the xml file that pnp4nagios automatically creates.
        '''
        
        # Initialize the dictionary that will be returned
        return_dict = {}
        
        tree = ET.parse(self.xml_path)
        root = tree.getroot()
        
        for datasource in root.findall('DATASOURCE'):
            key = datasource.find('DS').text
            value = datasource.find('NAME').text
            return_dict[key] = value           
            
        return return_dict
    
    def __init__(self,
                 invID,                                             # Inventory ID of host we are querying
                 perfdata_path='/usr/local/pnp4nagios/var/perfdata',  # Path to the pnp4nagios data
                 service_name='Interface_Traffic',                  # Name of the service that is being queried
                 graph_width=12096,                                 # Width of the graph (in steps)
                 graph_step=300,                                    # Default time of each graph step (in seconds)
                 out_file='foo',
                 start_time='end-6w',                               # Actual start time to graph
                 end_time='now',                                    # Actual end time to graph
                 print_format='%6.2lf',
                 debug=0,
                 ):                                   
        '''
        __init__ initializes the main data structures
        The rest of the rrdquery is put together using various commands, and then the actual query is made with the query command.
        '''
        self.debug          = debug
        self.rrd_path       = '{}/{}/{}.rrd'.format(perfdata_path, invID, service_name)
        self.xml_path       = '{}/{}/{}.xml'.format(perfdata_path, invID, service_name)
        self.rrd_info       = rrdtool.info(self.rrd_path)
        self.label_dict     = self.build_label_dict()
        self.ds_count       = len(self.label_dict) + 1
        self.command_list   = ['rrdtool',
                               'graph',
                               '--width',
                               str(graph_width),
                               '--step', str(graph_step),
                               out_file,
                               '--start',
                               '\'{}\''.format(start_time),
                               '--end',
                               '\'{}\''.format(end_time)]
        self.tokens         = {}
        self.print_format   = print_format
        
        
        if self.debug:
            sys.stderr.write('rrd info:\n')
            for item in self.rrd_info:
                sys.stderr.write('{}\n'.format(str(item)))
            sys.stderr.write('ds count = {}\n'.format(self.ds_count))
            sys.stderr.write('label dict:\n')
            sys.stderr.write('{}\n'.format(str(self.label_dict)))
        
    def define_dataset(self, name=None, consol_funct='avg'):
        '''
        define_dataset will generate rrd DEF commands and add them to the rrd query command list.
        If name is specified, it will only define datasets whose label (in label_dict) matches name.
        The function will return a list of tokens that have been defined as datasets.
        '''
        
        return_tokens   = []
        
        # Define a regex to match against the label
        if(name):
            name_search = re.compile(r'{}'.format(name))
        else:
            name_search = re.compile(r'.*')
            
        if self.debug:
            sys.stderr.write('{}\n'.format(name))
            
        for index in range(1, self.ds_count):
            if self.debug:
                sys.stderr.write('{}\n'.format(self.label_dict[str(index)]))
                
            # if (name_search.search(self.label_dict[str(index)])):
            if name in self.label_dict[str(index)]:
                ds_name = 'ds{}{}'.format(str(index), consol_funct)
                cmd_str = 'DEF:{2}={0}:{1}:{3}'.format(self.rrd_path, str(index), ds_name, cf_dict[consol_funct])
                self.command_list.append(cmd_str)
                return_tokens.append(ds_name)
                if self.debug:
                    sys.stderr.write('{}\n'.format(cmd_str))
                
        return return_tokens
                
    def define_vdef(self, name, rdef):
        '''
        define_vdef will generate an rrd VDEF command and add it to the query command list.
        '''
        
        cmd_str = 'VDEF:{}={}'.format(name, rdef)
        self.command_list.append(cmd_str)
        if self.debug:
            sys.stderr.write('{}\n'.format(cmd_str))
        
        return name
        
    
    def define_cdef(self, name, rdef):
        '''
        define_vdef will generate an rrd VDEF command and add it to the query command list.
        '''
        
        cmd_str = 'CDEF:{}={}'.format(name, rdef)
        self.command_list.append(cmd_str)
        if self.debug:
            sys.stderr.write('{}\n'.format(cmd_str))
            
        return name
        
    def define_print(self, vdef, format_arg=None):
        '''
        rrd_print will generate an rrd print command and append it to the query command list
        '''
        if format_arg:
            format_str = format_arg
        else:
            format_str = '{} = {}'.format(vdef, self.print_format)
            
        cmd_str = 'PRINT:{0}:\"{1}\"'.format(vdef, format_str)
        self.command_list.append(cmd_str)
        if self.debug:
            sys.stderr.write('{}\n'.format(cmd_str))
        
    def define_aggregate(self, name, datasets):
        '''
        define_aggregate takes a list of defined datasets, and creates an aggregate cdef from them.
        Generally the token list returned by define_dataset can be passed to this function for the datasets
        parameter. Name is the name you want to name the aggregate.
        
        The name of the aggregate is returned
        '''
        
        # Figure out the RPN rdef
        # Example output would be 'ds1,ds2,ds3,+,+' (= ds3 + ds2 + ds1)
        rdef_str = ''
        
        for ds in datasets:
            rdef_str += '{},'.format(ds)
            
        rdef_str += '+'
        
        count = len(datasets) - 2
        while count > 0:
            rdef_str += ',+'
            count -= 1
            
        # Create the cdef
        self.define_cdef(name, rdef_str)
        
        return name
            
        
    def define_prediction(self, cdef, step=604800, step_count=-5, window=1800):
        '''
        generate_prediction will generate the necessary rrd statements to make predictions based on history
        and adds them to the query command list.
        cdef is the calculated data variable to be predicted.
        step is the amount of time between samples in seconds. 1 week is default.
        step_count is the number of windowed samples to take. Default -5 is 5 samples back.
        window is the number of seconds in the window to sample. 1/2 hour default.
        A list of cdef tokens created by the function is returned.
        '''
        
        tokens = []
        basis_str   = '{},{},{},{}'.format(str(step),str(step_count),str(window),cdef)
        pred_name   = '{}_pred'.format(cdef)
        sig_name    = '{}_sigma'.format(cdef)
        
        
        tokens.append(self.define_cdef(pred_name, '{},PREDICT'.format(basis_str,cdef)))
        tokens.append(self.define_cdef(sig_name, '{},PREDICTSIGMA'.format(basis_str,cdef)))
        
        return tokens
        
    def run_query(self):
        '''
        run_query puts together the rrd query and then runs it in a subprocess
        '''
        
        if self.debug:
            for item in self.command_list:
                sys.stderr.write('{}\n'.format(item))
                
        # Create a single command string
        rrd_tool_cmd = ' '.join(self.command_list)
        
        if self.debug:
            sys.stderr.write('{}'.format(rrd_tool_cmd))
        
        # Run the command and store the output in a list
        # This runs as a subprocess because the python rrd module doesn't seem to work
        output = subprocess.Popen(rrd_tool_cmd, stdout=subprocess.PIPE, shell=True).stdout.read().split('\n')
        
        # Pop the first and last items on output - they are useless
        output.pop(0)
        output.pop()
        
        # Return the list
        return output
    
    
