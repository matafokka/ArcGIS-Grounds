"""
ArcGIS-Grounds
Copyright (C) 2019 matafokka
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Lesser General Public License for more details.
You should have received a copy of the GNU Lesser General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""

import arcpy
from os import mkdir
from os.path import splitext
from os import remove as rmv
from shutil import rmtree
from glob import glob

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "GroundsToolbox"
        self.alias = ""

        # List of tool classes associated with this toolbox
        self.tools = [GroundProcessor]


class GroundProcessor(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Ground Processor"
        self.description = """
        Processes grounds.
        <p><b>Caution!</b> This script will remove folder and shapefile with name of resulting file!</p>
        <h4>Parameters</h4>
        <p><b>Quarters Features</b> -- holds quarters. Quarters should look like grid and have Polyline type.</p>
        <p><b>Grounds Features</b> -- holds grounds. Will be cutted by quarters and rivers. Must have Polygon type.</p>
        <p><b>Rivers Features</b> -- holds rivers. Must have Polygon or Polyline type.</p>
        <p><b>Area</b> -- this script will dissolve polygons with area less than this parameter with neighbor with biggest distance if it's not crossed by quarter or river.</p>
        <p><b>Output</b> -- where you want to store results.</p>
        """
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        quarter_layer = arcpy.Parameter(
            displayName="Quarters Features",
            name="quarter_layer",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        quarter_layer.filter.list  = ["Polyline"]
        
        grounds_layer = arcpy.Parameter(
            displayName="Grounds Features",
            name="grounds_layer",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        grounds_layer.filter.list  = ["Polygon"]
        
        rivers_layer = arcpy.Parameter(
            displayName="Rivers Features",
            name="rivers_layer",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        rivers_layer.filter.list  = ["Polygon", "Polyline"]
        
        area = arcpy.Parameter(
            displayName="Dissolve polygons with area less or equal to (hectares)",
            name="area",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        
        output = arcpy.Parameter(
            displayName="Output Features",
            name="output",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Output")
        output.filter.list  = ["Polygon"]
        
        #               0               1             2        3      4
        params = [quarter_layer, grounds_layer, rivers_layer, area, output]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed. This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        arcpy.env.overwriteOutput = True # Allows functions to overwrite files
        # Put parameters into vars
        quarters, grounds, rivers, area, output = parameters[0].valueAsText, parameters[1].valueAsText, parameters[2].valueAsText, parameters[3].valueAsText, parameters[4].valueAsText
        
        # Define file paths
        path = output + "/"
        output_temp = path + "output_temp.shp"
        output = output + ".shp"
        # Splitting part
        small_polygons = path + "small_polygons.shp"
        # Parsing part
        current_polygon = path + "curr_polygon.shp"
        current_neighbors_uncut = path + "curr_nbrs_u.shp"
        current_neighbors = path + "curr_nbrs.shp"
        current_neighbor = path + "curr_nbr.shp"
        current_intersection = path + "curr_inter.shp"
        current_intersection_river = path + "curr_inter_rvr.shp"
        current_intersection_quarter = path + "curr_inter_q.shp"
        current_updated_polygon = path + "curr_upd_poly.shp"
        
        def removeFiles():
            try:
                rmtree(path)
            except:
                pass
        
        removeFiles()
        
        mkdir(path)
        if arcpy.Describe(rivers).shapeType == "Polyline":
            arcpy.FeatureToPolygon_management([grounds, quarters, rivers], output) # Split grounds by everything
        else:
            polygons_temp = path + "polygons_temp.shp"
            arcpy.FeatureToPolygon_management([grounds, quarters], output) # Split grounds by everything except rivers
            arcpy.Erase_analysis(output, rivers, polygons_temp) # Remove rivers from grounds
            arcpy.MultipartToSinglepart_management(polygons_temp, output) # Split multi parts to single parts
        
        # Add field with area
        area_field = "Shape_area"
        arcpy.AddField_management(output, area_field, "DOUBLE")
        
        # When script joins two small polygons, result's area may still be less than given.
        # So we need to re-run whole process for this polygon or for all small polygons left. Doesn't matter in matter of performance.
        # If last run didn't do anything then there are no small polygons left.
        didnt_do_anything = False
        while True:
            # Get small polygons depending on given area.
            arcpy.CalculateField_management(output, area_field, "!SHAPE.AREA@HECTARES!", "PYTHON_9.3")
            if didnt_do_anything:
                break
            didnt_do_anything = True # Now we didn't do anything
            arcpy.Select_analysis(output, small_polygons, '"' + area_field + '" <= ' + area)
            # Temporary layer for SelectLayerByLocation_management()
            temp_current = "current" # Current small polygon, used in first loop below
            temp_nbr = "temp_nbr"
        
            # Process all small grounds
            for ground in arcpy.da.SearchCursor(small_polygons, ["OID@"]):
                # Create file with current polygon and open it as layer
                arcpy.Select_analysis(small_polygons, current_polygon, '"FID" = ' + str(ground[0]))
                arcpy.MakeFeatureLayer_management(current_polygon, temp_current)
                
                # Find neighbors of current polygon
                arcpy.MakeFeatureLayer_management(output, temp_nbr)
                arcpy.SelectLayerByLocation_management(temp_nbr, "SHARE_A_LINE_SEGMENT_WITH", temp_current, selection_type = "NEW_SELECTION")
                arcpy.CopyFeatures_management(temp_nbr, current_neighbors_uncut)
                arcpy.Erase_analysis(current_neighbors_uncut, current_polygon, current_neighbors)
                
                # Process each neighbor
                # Values for largest neighbor
                max_area = 0
                max_nbr_oid = None
                for nbr in arcpy.da.SearchCursor(current_neighbors, ["OID@", "SHAPE@AREA"]):
                    # Create file with current neighbor
                    nbr_oid = str(nbr[0])
                    arcpy.Select_analysis(current_neighbors, current_neighbor, '"FID" = ' + nbr_oid)
                   
                    # Find if common edge of neighbor and current small ground is on river or quarter
                    arcpy.Intersect_analysis([temp_current, current_neighbor], current_intersection, "ALL", output_type = "LINE")
                    arcpy.Intersect_analysis([current_intersection, rivers], current_intersection_river, "ALL", output_type = "LINE")
                    arcpy.Intersect_analysis([current_intersection, quarters], current_intersection_quarter, "ALL", output_type = "LINE")
                    nbr_area = float(nbr[1])
                    
                    # If commong edge goes on river or quarter, intersection will return 1. 0 otherwise.
                    if nbr_area > max_area and arcpy.GetCount_management(current_intersection_river).getOutput(0) == "0" and arcpy.GetCount_management(current_intersection_quarter).getOutput(0) == "0":
                        max_area, max_nbr_oid = nbr_area, nbr_oid
                
                # Join ground with it's neighbor
                if max_nbr_oid is not None:
                    arcpy.Select_analysis(current_neighbors, current_neighbor, '"FID" = ' + str(max_nbr_oid)) # Get neighbor with found ID
                    arcpy.Update_analysis(current_neighbor, current_polygon, current_updated_polygon) # Add current ground to it's neighbor
                    arcpy.Dissolve_management(current_updated_polygon, current_polygon, "FID", multi_part = "SINGLE_PART") # Dissolve polygons in updated file
                    # Update output with new new whole polygon
                    arcpy.CopyFeatures_management(output, output_temp)
                    arcpy.Update_analysis(output_temp, current_polygon, output)
                    didnt_do_anything = False # Oh, we did something!
        
        # When quarters contains closed line, grounds will have ghost polygons.
        # Intersection of original grounds and result will fix this problem.
        arcpy.CopyFeatures_management(output, output_temp)
        arcpy.Intersect_analysis([output_temp, grounds], output)
        removeFiles()