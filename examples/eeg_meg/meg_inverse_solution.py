"""
Plot MEG inverse solution
=========================

Plot MEG inverse solution.

See the original example :

https://pysurfer.github.io/auto_examples/plot_meg_inverse_solution.html#sphx-glr-auto-examples-plot-meg-inverse-solution-py

.. image:: ../../picture/piceegmeg/ex_eegmeg_meg_inverse.png
"""
from visbrain import Brain
from visbrain.objects import BrainObj
from visbrain.io import path_to_visbrain_data, download_file, read_stc

"""Download file if needed :
"""
file = 'meg_source_estimate-lh.stc'
download_file(file)

# Read the *.stc file :
file = read_stc(path_to_visbrain_data(file=file))

# Get the data and vertices from the file :
data = file['data'][:, 2]
vertices = file['vertices']

# Define a brain object and add the data to the mesh :
b_obj = BrainObj('inflated', translucent=False, hemisphere='left')
b_obj.add_activation(data=data, vertices=vertices, smoothing_steps=5,
                     clim=(13., 22.), hide_under=13., cmap='plasma',
                     hemisphere='left')

# Finally, pass the brain object to the Brain module :
vb = Brain(brain_obj=b_obj)
vb.rotate('left')
vb.show()
