# Tech Bamboo Forest - Specification

## Project Overview
- **Project Name**: Tech Bamboo Forest
- **Type**: Single HTML interactive visual experience
- **Core Functionality**: A futuristic, cyberpunk-styled bamboo forest with glowing neon aesthetics and artistic atmosphere
- **Target Users**: Art enthusiasts, web visitors seeking immersive visual experiences

## Visual & Rendering Specification

### Scene Setup
- **Background**: Deep dark gradient (near black to dark teal) simulating night sky
- **Atmosphere**: Subtle mist/fog effect with parallax scrolling
- **Style**: Cyberpunk meets traditional Chinese ink painting

### Color Palette
- Primary: Cyan (#00ffff), Magenta (#ff00ff)
- Secondary: Electric blue (#00d4ff), Neon green (#39ff14)
- Background: Dark teal (#0a0a0f), Deep purple (#1a0a2e)
- Accents: Warm gold (#ffd700) for highlights

### Visual Elements

#### Bamboo Stalks
- 3-4 layers of bamboo at different depths (parallax)
- Glowing edges with neon light effect
- Slight sway animation mimicking wind
- Varied heights and thicknesses
- Circuit-like patterns etched on bamboo surface

#### Particle Effects
- Floating light particles (firefly-like)
- Data stream particles flowing upward
- Subtle dust motes in the air

#### Atmospheric Effects
- Animated fog/mist layers
- Light rays/shadows from above
- Subtle vignette effect

## Animation Specification

### Bamboo Animation
- Gentle swaying motion (CSS transform)
- Randomize animation duration for organic feel
- Duration: 3-6 seconds per sway cycle

### Particle Animation
- Particles float and drift slowly
- Upward-moving data particles
- Animation duration: 8-15 seconds loop

### Fog Animation
- Slow horizontal drift
- Multiple layers with different speeds
- Duration: 20-40 seconds per cycle

## Interaction Specification

### Mouse Interaction
- Parallax effect on mouse movement
- Bamboo reacts slightly to cursor proximity
- Subtle glow intensity change on hover areas

### Audio (Optional Enhancement)
- Ambient forest/electronic ambient sound
- Toggle button for sound

## Technical Implementation

### Structure
- Single HTML file with embedded CSS and JavaScript
- Canvas-based particle system
- CSS for bamboo and atmosphere styling
- No external dependencies (pure vanilla)

### Performance
- RequestAnimationFrame for smooth animations
- Efficient particle pooling
- CSS will-change hints for animated elements

## Acceptance Criteria
1. Bamboo forest renders with multiple depth layers
2. Neon glow effects visible on bamboo stalks
3. Smooth swaying animation on all bamboo elements
4. Floating particles create depth and atmosphere
5. Mouse parallax effect responds to cursor movement
6. Fog layers drift smoothly in background
7. Overall aesthetic is futuristic yet maintains bamboo forest essence
8. Works in modern browsers (Chrome, Firefox, Edge, Safari)
