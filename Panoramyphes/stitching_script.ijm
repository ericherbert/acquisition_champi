
stitchOptions  = " type=[Grid: snake by columns]"
stitchOptions += " order=[Down & Left]"
stitchOptions += " grid_size_x=%%x_size%% grid_size_y=%%y_size%%"
stitchOptions += " tile_overlap=%%overlap%%"
stitchOptions += " first_file_index_i=%%findex%%"
stitchOptions += " directory=[%%directory%%]"
stitchOptions += " file_names=%%filename%%{i}.png"
stitchOptions += " output_textfile_name=TileConfiguration_script.txt"
stitchOptions += " fusion_method=[Linear Blending]"
stitchOptions += " regression_threshold=0.30"
stitchOptions += " max/avg_displacement_threshold=4"
stitchOptions += " absolute_displacement_threshold=3"
stitchOptions += " compute_overlap"
stitchOptions += " ignore_z_stage"
stitchOptions += " computation_parameters=[Save memory (but be slower)]"
stitchOptions += " image_output=[Write to disk]"
stitchOptions += " output_directory=[%%output%%]"



run("Grid/Collection stitching", stitchOptions);
