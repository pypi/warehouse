http_path = "/"

css_dir = "warehouse/static/source/warehouse/css"
sass_dir = "warehouse/static/source/warehouse/sass"
images_dir = "warehouse/static/source/warehouse/images"
javascripts_dir = "warehouse/static/source/warehouse/js"
fonts_dir = "warehouse/static/source/warehouse/fonts"

# Output options.
relative_assets = true
line_comments = false
output_style = :compact


on_stylesheet_saved do |filename|
  system('wake')
end
