<h1>Evaluating pretrained GeoCLIP on different images</h1>
eval_geoclip.py takes an input csv file, locates the image using image_path value and then processes it using the pretrained geoclip model. The predicted lattitude, longitude is then appended to an output file, along with the spherical distance from the original latitude and longitude of the image.  
<br>
The script can be interrupted and once run again it will pick up from where it left off. User might need to fix the image_path for different cases.
<br><br>
Our aim would be to later on label the image categories and measure the performance of GeoCLIP on different image classes.
