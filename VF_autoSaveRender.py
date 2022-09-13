bl_info = {
	"name": "VF Auto Save Render",
	"author": "John Einselen - Vectorform LLC, based on work by tstscr(florianfelix)",
	"version": (1, 9, 0),
	"blender": (3, 2, 0),
	"location": "Rendertab > Output Panel > Subpanel",
	"description": "Automatically saves rendered images with custom naming convention",
	"warning": "inexperienced developer, use at your own risk",
	"wiki_url": "",
	"tracker_url": "",
	"category": "Render"}

# Based on the following resources:
# https://gist.github.com/egetun/1224aa600a32bd38fa771df463796977
# https://github.com/patrickhill/blender-datestamper/blob/master/render_auto_save_with_datestamp.py
# https://gist.github.com/robertguetzkow/8dacd4b565538d657b72efcaf0afe07e
# https://blender.stackexchange.com/questions/6842/how-to-get-the-directory-of-open-blend-file-from-python
# https://github.com/AlreadyLegendary/Render-time-estimator
# https://www.geeksforgeeks.org/python-program-to-convert-seconds-into-hours-minutes-and-seconds/
# https://blender.stackexchange.com/questions/196045/how-to-add-a-button-to-outliner-header-via-python-script
# https://stackoverflow.com/questions/4271740/how-can-i-use-python-to-get-the-system-hostname
# https://s-nako.work/2020/12/how-to-pass-arguments-to-custom-operator-in-blender-python/
# https://blender.stackexchange.com/questions/233803/call-a-dialog-box-without-ok-confirmation-button

import os
import platform
import datetime
import time
import bpy
from bpy.app.handlers import persistent
from re import findall, search, M as multiline
from pathlib import Path

IMAGE_FORMATS = (
	'BMP',
	'IRIS',
	'PNG',
	'JPEG',
	'JPEG2000',
	'TARGA',
	'TARGA_RAW',
	'CINEON',
	'DPX',
	'OPEN_EXR_MULTILAYER',
	'OPEN_EXR',
	'HDR',
	'TIFF')
IMAGE_EXTENSIONS = (
	'bmp',
	'rgb',
	'png',
	'jpg',
	'jp2',
	'tga',
	'cin',
	'dpx',
	'exr',
	'hdr',
	'tif'
)

variableArray = ["title,Project,SCENE_DATA", "{project}", "{scene}", "{collection}", "{camera}", "{item}",
				"title,Rendering,CAMERA_DATA", "{renderengine}", "{device}", "{samples}", "{features}", "{rendertime}",
				"title,System,DESKTOP", "{host}", "{version}",
				"title,Identifiers,COPY_ID", "{date}", "{time}", "{serial}", "{frame}"]

###########################################################################
# Auto save render function

@persistent
def auto_save_render(scene):
	# Set estimated render time active to false (render is complete or canceled, estimate display is no longer needed)
	bpy.context.scene.auto_save_render_settings.estimated_render_time_active = False

	# Calculate elapsed render time
	render_time = round(time.time() - float(bpy.context.scene.auto_save_render_settings.start_date), 2)

	# Update total render time
	bpy.context.scene.auto_save_render_settings.total_render_time = bpy.context.scene.auto_save_render_settings.total_render_time + render_time

	# Restore unprocessed file path if processing is enabled
	if bpy.context.preferences.addons['VF_autoSaveRender'].preferences.filter_output_file_path and bpy.context.scene.auto_save_render_settings.output_file_path:
		scene.render.filepath = bpy.context.scene.auto_save_render_settings.output_file_path

	# Restore unprocessed node output file path if processing is enabled, compositing is enabled, and a file output node exists with the default node name
	if bpy.context.preferences.addons['VF_autoSaveRender'].preferences.filter_output_file_node and bpy.context.scene.use_nodes and 'File Output' in bpy.context.scene.node_tree.nodes and bpy.context.scene.auto_save_render_settings.output_file_node:
		# bpy.context.scene.node_tree.nodes["File Output"].base_path = bpy.context.scene.auto_save_render_settings.output_file_node
		paths = bpy.context.scene.auto_save_render_settings.output_file_node
		# Split the saved string back into individual pieces
		paths = paths.split("||||")
		slotpaths = paths[1].split("||")

		# Replace node path and slots with the processed version
		bpy.context.scene.node_tree.nodes["File Output"].base_path = paths[0]
		for num, slot in enumerate(bpy.context.scene.node_tree.nodes["File Output"].file_slots):
			slot.path = slotpaths[num]

	# Stop here if the auto output is disabled
	if not bpy.context.scene.auto_save_render_settings.enable_auto_save_render or not bpy.data.filepath:
		return {'CANCELLED'}

	# Save original file format settings
	original_format = scene.render.image_settings.file_format
	original_colormode = scene.render.image_settings.color_mode
	original_colordepth = scene.render.image_settings.color_depth

	# Set up render output formatting
	if bpy.context.scene.auto_save_render_settings.file_format == 'SCENE':
		if original_format not in IMAGE_FORMATS:
			print('VF Auto Save Render: {} is not an image format. Image not saved.'.format(original_format))
			return
	elif bpy.context.scene.auto_save_render_settings.file_format == 'JPEG':
		scene.render.image_settings.file_format = 'JPEG'
	elif bpy.context.scene.auto_save_render_settings.file_format == 'PNG':
		scene.render.image_settings.file_format = 'PNG'
	elif bpy.context.scene.auto_save_render_settings.file_format == 'OPEN_EXR':
		scene.render.image_settings.file_format = 'OPEN_EXR'
	extension = scene.render.file_extension

	# Set location and file name variables
	projectname = os.path.splitext(os.path.basename(bpy.data.filepath))[0]

	if len(bpy.context.scene.auto_save_render_settings.file_location) <= 1:
		filepath = os.path.join(os.path.dirname(bpy.data.filepath), projectname)
	else:
		filepath = bpy.context.scene.auto_save_render_settings.file_location

	# Create the project subfolder if it doesn't already exist
	if not os.path.exists(filepath):
		os.makedirs(filepath)

	# Create the output file name string
	if bpy.context.scene.auto_save_render_settings.file_name_type == 'SERIAL':
		# Generate dynamic serial number
		# Finds all of the image files that start with projectname in the selected directory
		files = [f for f in os.listdir(filepath)
				if f.startswith(projectname)
				and f.lower().endswith(IMAGE_EXTENSIONS)]
		# Searches the file collection and returns the next highest number as a 4 digit string
		def save_number_from_files(files):
			highest = 0
			if files:
				for f in files:
					# find filenames that end with four or more digits
					suffix = findall(r'\d{4,}$', os.path.splitext(f)[0].split(projectname)[-1], multiline)
					if suffix:
						if int(suffix[-1]) > highest:
							highest = int(suffix[-1])
			return format(highest+1, '04')
		# Create string with serial number
		filename = '{project}-' + save_number_from_files(files)
	elif bpy.context.scene.auto_save_render_settings.file_name_type == 'DATE':
		filename = '{project} {date} {time}'
	elif bpy.context.scene.auto_save_render_settings.file_name_type == 'RENDER':
		# Render time is not availble in the global variable replacement becuase it's computed in the above section of code, not universally available
		filename = '{project} {renderengine} ' + str(render_time)
	else:
		# Load custom file name and process elements that aren't available in the global variable replacement
		filename = bpy.context.scene.auto_save_render_settings.file_name_custom
		filename = filename.replace("{rendertime}", str(render_time))
		# Remember that auto save serial number is separate from the project serial number, which is handled in the global variable function
		if '{serial}' in filename:
			filename = filename.replace("{serial}", format(bpy.context.scene.auto_save_render_settings.file_name_serial, '04'))
			bpy.context.scene.auto_save_render_settings.file_name_serial += 1

	# Replace global variables in the output file name string
	filename = replaceVariables(filename)

	# Add extension
	filename += extension

	# Combine file path and file name using system separator
	filename = os.path.join(filepath, filename)

	# Save image file
	image = bpy.data.images['Render Result']
	if not image:
		print('VF Auto Save Render: Render Result not found. Image not saved.')
		return

	# Please note that multilayer EXR files are currently unsupported in the Python API - https://developer.blender.org/T71087
	image.save_render(filename, scene=None) # Might consider using bpy.context.scene if different compression settings are desired per-scene?

	# Restore original user settings for render output
	scene.render.image_settings.file_format = original_format
	scene.render.image_settings.color_mode = original_colormode
	scene.render.image_settings.color_depth = original_colordepth

	# Save external log file
	if bpy.context.preferences.addons['VF_autoSaveRender'].preferences.external_render_time:
		# Log file settings
		logname = bpy.context.preferences.addons['VF_autoSaveRender'].preferences.external_log_name
		logname = logname.replace("{project}", projectname)
		logpath = os.path.join(os.path.dirname(bpy.data.filepath), logname) # Limited to locations local to the project file
		logtitle = 'Total Render Time: '
		logtime = 0.00

		# Get previous time spent rendering, if log file exists, and convert formatted string into seconds
		if os.path.exists(logpath):
			with open(logpath) as filein:
				logtime = filein.read().replace(logtitle, '')
				logtime = readableToSeconds(logtime)
		# Create log file directory location if it doesn't exist
		elif not os.path.exists(os.path.dirname(logpath)): # Safety net just in case a folder was included in the file name entry
			os.makedirs(os.path.dirname(logpath))

		# Add the latest render time
		logtime += float(render_time)

		# Convert seconds into formatted string
		logtime = secondsToReadable(logtime)

		# Write log file
		with open(logpath, 'w') as fileout:
			fileout.write(logtitle + logtime)

	return {'FINISHED'}

###########################################################################
# Start time function

@persistent
def auto_save_render_start(scene):
	# Set estimated render time active to false (must render at least one frame before estimating time remaining)
	bpy.context.scene.auto_save_render_settings.estimated_render_time_active = False

	# Save start time in seconds as a string to the addon settings
	bpy.context.scene.auto_save_render_settings.start_date = str(time.time())

	# Track usage of the global serial number in both file output and output nodes to ensure it's only incremented once
	serialUsed = False

	# Filter output file path if enabled
	if bpy.context.preferences.addons['VF_autoSaveRender'].preferences.filter_output_file_path:
		# Save original file path
		bpy.context.scene.auto_save_render_settings.output_file_path = filepath = scene.render.filepath

		# Check if the serial variable is used
		if '{serial}' in filepath:
			filepath = filepath.replace("{serial}", format(bpy.context.scene.auto_save_render_settings.output_file_serial, '04'))
			serialUsed = True

		# Replace scene filepath output with the processed version
		scene.render.filepath = replaceVariables(filepath)

	# Filter compositing node file path if enabled
	# Trusting the short-circuit boolean expression ("not technically lazy") evaluation in Python means this lengthy series of ANDs doesn't run into any issues at the end if the node doesn't exist
	if bpy.context.preferences.addons['VF_autoSaveRender'].preferences.filter_output_file_node and bpy.context.scene.use_nodes and 'File Output' in bpy.context.scene.node_tree.nodes and not bpy.context.scene.node_tree.nodes["File Output"].mute:
		# Get file path
		# filepath = bpy.context.scene.node_tree.nodes["File Output"].base_path

		# Get file path and all output file names
		paths = [bpy.context.scene.node_tree.nodes["File Output"].base_path + '||']
		for slot in bpy.context.scene.node_tree.nodes["File Output"].file_slots:
			paths.append(slot.path)
		paths = '||'.join(paths)

		# Save original paths
		bpy.context.scene.auto_save_render_settings.output_file_node = paths

		# Check if the serial variable is used
		if '{serial}' in paths:
			paths = paths.replace("{serial}", format(bpy.context.scene.auto_save_render_settings.output_file_serial, '04'))
			serialUsed = True

		# Process entire string
		paths = replaceVariables(paths)

		# Split the string back into individual pieces (this is the STUPIDEST solution, but I'm not confident I can do it in any sort of respectable way while also storing the original string in a Blender preference to be restored later)
		paths = paths.split("||||")
		slotpaths = paths[1].split("||")

		# Replace node path and slots with the processed version
		bpy.context.scene.node_tree.nodes["File Output"].base_path = paths[0]
		for num, slot in enumerate(bpy.context.scene.node_tree.nodes["File Output"].file_slots):
			slot.path = slotpaths[num]
		# bpy.context.scene.node_tree.nodes["File Output"].base_path = replaceVariables(filepath)

	# Increment the serial number if it was used once or more
	if serialUsed:
		bpy.context.scene.auto_save_render_settings.output_file_serial += 1

###########################################################################
# Render time remaining estimation function
		
@persistent
def auto_save_render_estimate(scene):
	# Save starting frame (before setting active to true, this should only happen once during a sequence)
	if not bpy.context.scene.auto_save_render_settings.estimated_render_time_active:
		bpy.context.scene.auto_save_render_settings.estimated_render_time_frame = bpy.context.scene.frame_current

	# If it's not the last frame, estimate time remaining
	if bpy.context.scene.frame_current < bpy.context.scene.frame_end:
		bpy.context.scene.auto_save_render_settings.estimated_render_time_active = True
		# Elapsed time (Current - Render Start)
		render_time = time.time() - float(bpy.context.scene.auto_save_render_settings.start_date)
		# Divide by number of frames completed
		render_time /= bpy.context.scene.frame_current - bpy.context.scene.auto_save_render_settings.estimated_render_time_frame + 1.0
		# Multiply by number of frames assumed unrendered (does not account for previously completed frames beyond the current frame)
		render_time *= bpy.context.scene.frame_end - bpy.context.scene.frame_current
		# Convert to readable and store
		bpy.context.scene.auto_save_render_settings.estimated_render_time_value = secondsToReadable(render_time)
		# print('Estimated Time Remaining: ' + bpy.context.scene.auto_save_render_settings.estimated_render_time_value)
	else:
		bpy.context.scene.auto_save_render_settings.estimated_render_time_active = False

###########################################################################
# Variable replacement function for globally accessible variables (serial number must be provided)
# Excludes {rendertime} as it does not exist at the start of rendering

def replaceVariables(string):
	# Get render engine feature sets
	if bpy.context.engine == 'BLENDER_WORKBENCH':
		engineDevice = 'GPU'
		engineSamples = bpy.context.scene.display.render_aa
		engineFeatures = bpy.context.scene.display.shading.light

	elif bpy.context.engine == 'BLENDER_EEVEE':
		engineDevice = 'GPU'
		engineSamples = str(bpy.context.scene.eevee.taa_render_samples) + '-' + str(bpy.context.scene.eevee.sss_samples) + '-' + str(bpy.context.scene.eevee.volumetric_samples)
		engineFeaturesArray = []
		if bpy.context.scene.eevee.use_gtao:
			engineFeaturesArray.append('AO')
		if bpy.context.scene.eevee.use_bloom:
			engineFeaturesArray.append('Bloom')
		if bpy.context.scene.eevee.use_ssr:
			engineFeaturesArray.append('SSR')
		if bpy.context.scene.eevee.use_motion_blur:
			engineFeaturesArray.append('MB')
		engineFeatures = 'None' if len(engineFeaturesArray) == 0 else '+'.join(engineFeaturesArray)

	elif bpy.context.engine == 'CYCLES':
		engineDevice = bpy.context.scene.cycles.device
		# Add compute device type if GPU is enabled
		# if engineDevice == "GPU":
			# engineDevice += '_' + bpy.context.preferences.addons["cycles"].preferences.compute_device_type
		engineSamples = str(round(bpy.context.scene.cycles.adaptive_threshold, 4)) + '-' + str(bpy.context.scene.cycles.samples) + '-' + str(bpy.context.scene.cycles.adaptive_min_samples)
		engineFeatures = str(bpy.context.scene.cycles.max_bounces) + '-' + str(bpy.context.scene.cycles.diffuse_bounces) + '-' + str(bpy.context.scene.cycles.glossy_bounces) + '-' + str(bpy.context.scene.cycles.transmission_bounces) + '-' + str(bpy.context.scene.cycles.volume_bounces) + '-' + str(bpy.context.scene.cycles.transparent_max_bounces)

	elif bpy.context.engine == 'RPR':
		# Compile array of enabled devices
		engineDevicesArray = []
		if bpy.context.preferences.addons["rprblender"].preferences.settings.final_devices.cpu_state:
			engineDevicesArray.append('CPU')
		for gpu in bpy.context.preferences.addons["rprblender"].preferences.settings.final_devices.available_gpu_states:
			if gpu:
				engineDevicesArray.append('GPU')
		engineDevice = 'None' if len(engineDevicesArray) == 0 else '+'.join(engineDevicesArray)
		engineSamples = str(bpy.context.scene.rpr.limits.min_samples) + '-' + str(bpy.context.scene.rpr.limits.max_samples) + '-' + str(round(bpy.context.scene.rpr.limits.noise_threshold, 4))
		engineFeatures = str(bpy.context.scene.rpr.max_ray_depth) + '-' + str(bpy.context.scene.rpr.diffuse_depth) + '-' + str(bpy.context.scene.rpr.glossy_depth) + '-' + str(bpy.context.scene.rpr.refraction_depth) + '-' + str(bpy.context.scene.rpr.glossy_refraction_depth) + '-' + str(bpy.context.scene.rpr.shadow_depth)

	else:
		engineDevice = 'unknown'
		engineSamples = 'unknown'
		engineFeatures = 'unknown'

	# Using "replace" instead of "format" because format fails ungracefully when an exact match isn't found (unusable behaviour in this situation)
	# Project variables
	string = string.replace("{project}", os.path.splitext(os.path.basename(bpy.data.filepath))[0])
	string = string.replace("{scene}", bpy.context.scene.name)
	string = string.replace("{collection}", bpy.context.collection.name)
	string = string.replace("{camera}", bpy.context.scene.camera.name)
	string = string.replace("{item}", bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else 'None')
	# Rendering variables
	string = string.replace("{renderengine}", bpy.context.engine.replace('BLENDER_', ''))
	string = string.replace("{device}", engineDevice)
	string = string.replace("{samples}", engineSamples)
	string = string.replace("{features}", engineFeatures)
		# {rendertime} is handled elsewhere
	# System variables
	string = string.replace("{host}", platform.node().split('.')[0])
	string = string.replace("{version}", bpy.app.version_string + '-' + bpy.app.version_cycle)
	# Identifier variables
	string = string.replace("{date}", datetime.datetime.now().strftime('%Y-%m-%d'))
	string = string.replace("{time}", datetime.datetime.now().strftime('%H-%M-%S'))
		# {serial} is handled elsewhere
	string = string.replace("{frame}", format(bpy.context.scene.frame_current, '04'))
	return string

###########################################################################
# Time conversion functions, because datetime doesn't like zero-numbered days or hours over 24

# Converts float into HH:MM:SS.## format, hours expand indefinitely (will not roll over into days)
def secondsToReadable(seconds):
	seconds, decimals = divmod(seconds, 1)
	minutes, seconds = divmod(seconds, 60)
	hours, minutes = divmod(minutes, 60)
	return "%d:%02d:%02d.%02d" % (hours, minutes, seconds, round(decimals*100))

# Converts string of HH:MM:SS.## format into float
def readableToSeconds(readable):
	hours, minutes, seconds = readable.split(':')
	return int(hours)*3600 + int(minutes)*60 + float(seconds)

###########################################################################
# UI input functions

def set_directory(self, value):
	path = Path(value)
	if path.is_dir():
		self["file_location"] = value

def get_directory(self):
	return self.get("file_location", bpy.context.scene.auto_save_render_settings.bl_rna.properties["file_location"].default)

###########################################################################
# Global user preferences and UI rendering class

class AutoSaveRenderPreferences(bpy.types.AddonPreferences):
	bl_idname = __name__

	# Global Variables
	filter_output_file_path: bpy.props.BoolProperty(
		name='Process Output File Path',
		description='Implements most of the same keywords used in the custom naming scheme in the Output directory',
		default=True)
	filter_output_file_node: bpy.props.BoolProperty(
		name='Process "File Output" Compositing Node',
		description='Implements most of the same keywords used in the custom naming scheme in a Compositing tab "File Output" node',
		default=True)
	show_total_render_time: bpy.props.BoolProperty(
		name="Show Internal Total Render Time",
		description='Displays the total time spent rendering a project in the output panel',
		default=True)
	external_render_time: bpy.props.BoolProperty(
		name="Save External Render Time Log",
		description='Saves the total time spent rendering to an external log file',
		default=False)
	external_log_name: bpy.props.StringProperty(
		name="File Name",
		description="Log file name; use {project} for per-project tracking, remove it for per-directory tracking",
		default="{project}-TotalRenderTime.txt",
		maxlen=4096)
	remaining_render_time: bpy.props.BoolProperty(
		name="Display Estimated Remaining Render Time",
		description='Adds estimated remaining render time display to the image editor menu',
		default=True)

	# User Interface
	def draw(self, context):
		layout = self.layout
		# layout.label(text="Addon Default Preferences")
		grid0 = layout.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=False, align=False)
		grid0.prop(self, "filter_output_file_path")
		grid0.prop(self, "filter_output_file_node")

		grid1 = layout.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=False, align=False)
		grid1.prop(self, "show_total_render_time")
		if bpy.context.preferences.addons['VF_autoSaveRender'].preferences.show_total_render_time:
			grid1.prop(context.scene.auto_save_render_settings, 'total_render_time')

		grid2 = layout.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=False, align=False)
		grid2.prop(self, "external_render_time")
		if bpy.context.preferences.addons['VF_autoSaveRender'].preferences.external_render_time:
			grid2.prop(self, "external_log_name", text='')

		layout.prop(self, "remaining_render_time")

###########################################################################
# Individual project settings

class AutoSaveRenderSettings(bpy.types.PropertyGroup):
	enable_auto_save_render: bpy.props.BoolProperty(
		name="Enable/disable automatic saving of rendered images",
		description="Automatically saves numbered or dated images in a directory alongside the project file or in a custom location",
		default=True)
	file_location: bpy.props.StringProperty(
		name="Autosave Location",
		description="Leave a single forward slash to auto generate folders alongside project files",
		default="/",
		maxlen=4096,
		subtype="DIR_PATH",
		set=set_directory,
		get=get_directory)
	file_name_type: bpy.props.EnumProperty(
		name='File Name',
		description='Auto saves files with the project name and serial number, project name and date, or custom naming pattern',
		items=[
			('SERIAL', 'Project Name + Serial Number', 'Save files with a sequential serial number'),
			('DATE', 'Project Name + Date & Time', 'Save files with the local date and time'),
			('RENDER', 'Project Name + Render Engine + Render Time', 'Save files with the render engine and render time'),
			('CUSTOM', 'Custom String', 'Save files with a custom string format'),
			],
		default='SERIAL')
	file_name_custom: bpy.props.StringProperty(
		name="Custom String",
		description="Format a custom string using the variables listed below",
		default="{project}-{serial}-{renderengine}-{rendertime}",
		maxlen=4096)
	file_name_serial: bpy.props.IntProperty(
		name="Serial Number",
		description="Current serial number, automatically increments with every render")
	file_format: bpy.props.EnumProperty(
		name='File Format',
		description='Image format used for the automatically saved render files',
		items=[
			('SCENE', 'Project Setting', 'Same format as set in output panel'),
			('PNG', 'PNG', 'Save as png'),
			('JPEG', 'JPEG', 'Save as jpeg'),
			('OPEN_EXR', 'OpenEXR', 'Save as exr'),
			],
		default='JPEG')

	# Variables for render time calculation
	start_date: bpy.props.StringProperty(
		name="Render Start Date",
		description="Stores the date when rendering started in seconds as a string",
		default="")
	total_render_time: bpy.props.FloatProperty(
		name="Total Render Time",
		description="Stores the total time spent rendering in seconds",
		default=0)

	# Variables for render time estimation
	estimated_render_time_active: bpy.props.BoolProperty(
		name="Render Active",
		description="Indicates if rendering is currently active",
		default=False)
	estimated_render_time_frame: bpy.props.IntProperty(
		name="Starting frame",
		description="Saves the starting frame when render begins (helps correctly estimate partial renders)",
		default=0)
	estimated_render_time_value: bpy.props.StringProperty(
		name="Estimated Render Time",
		description="Stores the estimated time remaining to render",
		default="0:00:00.00")

	# Variables for output file path processing
	output_file_path: bpy.props.StringProperty(
		name="Original Render Path",
		description="Stores the original render path as a string to allow for successful restoration after rendering completes",
		default="")
	output_file_node: bpy.props.StringProperty(
		name="Original Node Path",
		description="Stores the original node path as a string to allow for successful restoration after rendering completes",
		default="")
	output_file_serial: bpy.props.IntProperty(
		name="Serial Number",
		description="Current serial number, automatically increments with every render")


###########################################################################
# UI rendering classes

class RENDER_PT_auto_save_render(bpy.types.Panel):
	bl_space_type = 'PROPERTIES'
	bl_region_type = 'WINDOW'
	bl_context = "render"
	bl_label = "Auto Save Render"
	bl_parent_id = "RENDER_PT_output"
	# bl_options = {'DEFAULT_CLOSED'}

	# Check for engine compatibility
	# compatible_render_engines = {'BLENDER_RENDER', 'BLENDER_OPENGL', 'BLENDER_WORKBENCH', 'BLENDER_EEVEE', 'CYCLES', 'RPR', 'LUXCORE'}
	# @classmethod
	# def poll(cls, context):
		# return (context.engine in cls.compatible_render_engines)

	def draw_header(self, context):
		self.layout.prop(context.scene.auto_save_render_settings, 'enable_auto_save_render', text='')

	def draw(self, context):
		layout = self.layout
		layout.use_property_decorate = False  # No animation
		layout.prop(context.scene.auto_save_render_settings, 'file_location', text='')
		layout.use_property_split = True
		layout.prop(context.scene.auto_save_render_settings, 'file_name_type', icon='FILE_TEXT')
		if bpy.context.scene.auto_save_render_settings.file_name_type == 'CUSTOM':
			layout.use_property_split = True
			layout.prop(context.scene.auto_save_render_settings, 'file_name_custom')
			if '{serial}' in bpy.context.scene.auto_save_render_settings.file_name_custom:
				layout.use_property_split = True
				layout.prop(context.scene.auto_save_render_settings, 'file_name_serial')
		layout.prop(context.scene.auto_save_render_settings, 'file_format', icon='FILE_IMAGE')
		if bpy.context.scene.auto_save_render_settings.file_format == 'SCENE' and bpy.context.scene.render.image_settings.file_format == 'OPEN_EXR_MULTILAYER':
			error = layout.box()
			error.label(text="Warning: Blender Python API does not support saving multilayer EXR files")
			error.label(text="Report: https://developer.blender.org/T71087")
			error.label(text="Result: single layer EXR file will be saved instead")
		if bpy.context.preferences.addons['VF_autoSaveRender'].preferences.show_total_render_time or bpy.context.scene.auto_save_render_settings.file_name_type == 'CUSTOM':
			box = layout.box()
			if bpy.context.preferences.addons['VF_autoSaveRender'].preferences.show_total_render_time:
				box.label(text="Total time spent rendering: "+secondsToReadable(bpy.context.scene.auto_save_render_settings.total_render_time))
			if bpy.context.scene.auto_save_render_settings.file_name_type == 'CUSTOM':
				grid = box.grid_flow(columns=4, even_columns=True, even_rows=False)
				for item in variableArray:
					# Display headers
					if item.startswith("title,"):
						x = item.split(",")
						col = grid.column(align=True)
						col.label(text = x[1], icon = x[2])
					# Display list elements
					else:
						col.label(text = item)

# Time estimate display within the Image viewer
def estimated_render_time(self, context):
	if bpy.context.preferences.addons['VF_autoSaveRender'].preferences.remaining_render_time and bpy.context.scene.auto_save_render_settings.estimated_render_time_active:
		self.layout.separator()
		box = self.layout.box()
		box.label(text="  Estimated Time Remaining: " + bpy.context.scene.auto_save_render_settings.estimated_render_time_value + "")

###########################################################################
# Variable info popup

# bpy.context.window_manager.clipboard = "test"

class AutoSaveRenderVariablePopup(bpy.types.Operator):
	"""List of the available variables"""
	bl_label = "Variable List"
	bl_idname = "vf.auto_save_render_variable_popup"
	bl_options = {'REGISTER', 'INTERNAL'}

	rendertime: bpy.props.BoolProperty()

	@classmethod
	def poll(cls, context):
		return True

	def execute(self, context):
		self.report({'INFO'}, "YES")
		return {'FINISHED'}

	def invoke(self, context, event):
		return context.window_manager.invoke_popup(self, width=400)

	def draw(self, context):
		layout = self.layout
		grid = self.layout.grid_flow(columns=4, even_columns=True, even_rows=False)
		for item in variableArray:
			# Display headers
			if item.startswith("title,"):
				x = item.split(",")
				col = grid.column()
#				col.alignment = "LEFT"
				col.label(text = x[1], icon = x[2])
			# Display list elements
			elif item != "{rendertime}" or self.rendertime:
#				col.alignment = "RIGHT"
				col.label(text = item)

def RENDER_PT_output_path_variable_list(self, context):
	if not (False):
		layout = self.layout
		layout.use_property_decorate = False  # No animation
		layout.use_property_split = True
		if bpy.context.preferences.addons['VF_autoSaveRender'].preferences.filter_output_file_path:
			row = layout.row()
			if '{serial}' in bpy.context.scene.render.filepath:
				row.prop(context.scene.auto_save_render_settings, 'output_file_serial')
				row.scale_x = 1.0
			else:
				row.label(text="")
				row.scale_x = 1.5
			ops = row.operator(AutoSaveRenderVariablePopup.bl_idname, text = "Variable List", icon = "LINENUMBERS_OFF")
			ops.rendertime = False

def NODE_PT_output_path_variable_list(self, context):
	if not (False) and bpy.context.preferences.addons['VF_autoSaveRender'].preferences.filter_output_file_node:
		layout = self.layout
		layout.use_property_decorate = False  # No animation
		layout.use_property_split = True
		row = layout.row()
		row.label(text="")
		row.scale_x = 1.5
		ops = row.operator(AutoSaveRenderVariablePopup.bl_idname, text = "Variable List", icon = "LINENUMBERS_OFF") # LINENUMBERS_OFF, THREE_DOTS, SHORTDISPLAY, ALIGN_JUSTIFY
		ops.rendertime = False

###########################################################################
# Addon registration functions

classes = (AutoSaveRenderPreferences, AutoSaveRenderSettings, RENDER_PT_auto_save_render, AutoSaveRenderVariablePopup)

def register():
	for cls in classes:
		bpy.utils.register_class(cls)
	bpy.types.Scene.auto_save_render_settings = bpy.props.PointerProperty(type=AutoSaveRenderSettings)
	# Using init instead of render_pre means that the entire animation render time is tracked instead of just the final frame
	# bpy.app.handlers.render_pre.append(auto_save_render_start)
	bpy.app.handlers.render_init.append(auto_save_render_start)
	# Using render_post to calculate estimated time remaining only for animations (when more than one frame is rendered in sequence)
	bpy.app.handlers.render_post.append(auto_save_render_estimate)
	# Using cancel and complete, instead of render_post, prevents saving an image for every frame in an animation
	# bpy.app.handlers.render_post.append(auto_save_render)
	bpy.app.handlers.render_cancel.append(auto_save_render)
	bpy.app.handlers.render_complete.append(auto_save_render)
	# Render estimate display
	bpy.types.IMAGE_MT_editor_menus.append(estimated_render_time)
	# Variable info popup
	bpy.types.RENDER_PT_output.prepend(RENDER_PT_output_path_variable_list)
	bpy.types.NODE_PT_active_node_properties.prepend(NODE_PT_output_path_variable_list)

def unregister():
	for cls in reversed(classes):
		bpy.utils.unregister_class(cls)
	del bpy.types.Scene.auto_save_render_settings
	# Using init instead of render_pre means that the entire animation render time is tracked instead of just the final frame
	# bpy.app.handlers.render_pre.remove(auto_save_render_start)
	bpy.app.handlers.render_init.remove(auto_save_render_start)
	# Using render_post to calculate estimated time remaining only for animations (when more than one frame is rendered in sequence)
	bpy.app.handlers.render_post.remove(auto_save_render_estimate)
	# Using cancel and complete, instead of render_post, prevents saving an image for every frame in an animation
	# bpy.app.handlers.render_post.remove(auto_save_render)
	bpy.app.handlers.render_cancel.remove(auto_save_render)
	bpy.app.handlers.render_complete.remove(auto_save_render)
	# Render estimate display
	bpy.types.IMAGE_MT_editor_menus.remove(estimated_render_time)
	# Variable info popup
	bpy.types.RENDER_PT_output.remove(RENDER_PT_output_path_variable_list)
	bpy.types.NODE_PT_active_node_properties.remove(NODE_PT_output_path_variable_list)

if __name__ == "__main__":
	register()