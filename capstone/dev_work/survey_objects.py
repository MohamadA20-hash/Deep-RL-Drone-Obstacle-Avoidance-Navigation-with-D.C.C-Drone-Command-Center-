"""Quick scene object survey - uses AirSim API to list all objects and positions."""
import airsim
import json

client = airsim.MultirotorClient()
client.confirmConnection()

# List all scene objects
objects = client.simListSceneObjects('.*')
print(f'Total objects: {len(objects)}')

# Get positions of all objects
building_data = []
for obj in objects:
    try:
        pose = client.simGetObjectPose(obj)
        scale = client.simGetObjectScale(obj)
        entry = {
            'name': obj,
            'x': round(pose.position.x_val, 1),
            'y': round(pose.position.y_val, 1),
            'z': round(pose.position.z_val, 1),
            'sx': round(scale.x_val, 1) if scale else 0,
            'sy': round(scale.y_val, 1) if scale else 0,
            'sz': round(scale.z_val, 1) if scale else 0,
        }
        building_data.append(entry)
    except:
        pass

# Sort by distance from origin
building_data.sort(key=lambda b: (b['x']**2 + b['y']**2)**0.5)

# Print all with meaningful size
print(f'\nLarge objects (potential obstacles):')
for b in building_data:
    size = max(b['sx'], b['sy'], b['sz'])
    if size >= 1.0:
        dist = (b['x']**2 + b['y']**2)**0.5
        print(f"  {b['name']:50s} pos=({b['x']:8.1f},{b['y']:8.1f},{b['z']:7.1f}) "
              f"scale=({b['sx']:.1f},{b['sy']:.1f},{b['sz']:.1f}) dist={dist:.0f}m")

# Save full data
with open('scene_objects.json', 'w') as f:
    json.dump(building_data, f, indent=2)
print(f'\nSaved {len(building_data)} objects to scene_objects.json')
