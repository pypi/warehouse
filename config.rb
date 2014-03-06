require 'pathname'

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
  saved = Pathname.new(filename)
  rel_saved = saved.relative_path_from(Pathname.new(Dir.pwd))
  rel2 = rel_saved.relative_path_from(Pathname.new('warehouse/static/source'))
  rel3 = rel2.to_s().chomp(File.extname(rel2))

  FileUtils.rm(Dir["warehouse/static/compiled/**/#{File.basename(rel3)}-*#{File.extname(rel2)}"])

  system('wake') or raise("There was an error running wake")  # TODO: Figure out how to do this better

  system('python -m whitenoise.gzip -q warehouse/static/compiled')
end
