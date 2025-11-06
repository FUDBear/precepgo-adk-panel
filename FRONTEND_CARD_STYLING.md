# Frontend Card Styling - Background Image with Gradient Fade

## CSS Styling for Scenario Cards with Background Image

Add this CSS to your frontend application to display the generated image behind the card text with a white gradient fade:

```css
/* Patient Information Card */
.patient-info-card {
    position: relative;
    padding: 20px;
    border-radius: 8px;
    background-color: white;
    overflow: hidden;
}

.patient-info-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-image: url('YOUR_IMAGE_URL_HERE');
    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;
    opacity: 0.3; /* Adjust opacity (0-1) */
    z-index: 0;
}

.patient-info-card::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(
        to bottom,
        rgba(255, 255, 255, 0.9) 0%,
        rgba(255, 255, 255, 0.7) 30%,
        rgba(255, 255, 255, 0.5) 60%,
        rgba(255, 255, 255, 0.95) 100%
    );
    z-index: 1;
}

.patient-info-card > * {
    position: relative;
    z-index: 2; /* Content above gradient */
}

/* Scenario Card */
.scenario-card {
    position: relative;
    padding: 20px;
    border-radius: 8px;
    background-color: white;
    overflow: hidden;
}

.scenario-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-image: url('YOUR_IMAGE_URL_HERE');
    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;
    opacity: 0.25; /* Slightly more transparent for text readability */
    z-index: 0;
}

.scenario-card::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(
        to bottom,
        rgba(255, 255, 255, 0.85) 0%,
        rgba(255, 255, 255, 0.6) 25%,
        rgba(255, 255, 255, 0.4) 50%,
        rgba(255, 255, 255, 0.6) 75%,
        rgba(255, 255, 255, 0.9) 100%
    );
    z-index: 1;
}

.scenario-card > * {
    position: relative;
    z-index: 2; /* Content above gradient */
}
```

## HTML Example

```html
<!-- Patient Information Card -->
<div class="patient-info-card" style="background-image: url('{{scenario.image}}');">
    <h3>Patient Information</h3>
    <p><strong>Name:</strong> {{patient.name}}</p>
    <p><strong>Age:</strong> {{patient.age}}</p>
    <div>
        <span class="tag">{{category}}</span>
    </div>
</div>

<!-- Scenario Card -->
<div class="scenario-card" style="background-image: url('{{scenario.image}}');">
    <h3>Scenario</h3>
    <p>{{scenario.description}}</p>
</div>
```

## Inline Style Version (for React/Vue/Dynamic)

If you're using a framework and need inline styles, use this approach:

```html
<div style="
    position: relative;
    padding: 20px;
    border-radius: 8px;
    background-color: white;
    overflow: hidden;
">
    <!-- Background Image Layer -->
    <div style="
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background-image: url('{{scenario.image}}');
        background-size: cover;
        background-position: center;
        opacity: 0.3;
        z-index: 0;
    "></div>
    
    <!-- Gradient Fade Layer -->
    <div style="
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(
            to bottom,
            rgba(255, 255, 255, 0.9) 0%,
            rgba(255, 255, 255, 0.7) 30%,
            rgba(255, 255, 255, 0.5) 60%,
            rgba(255, 255, 255, 0.95) 100%
        );
        z-index: 1;
    "></div>
    
    <!-- Content Layer -->
    <div style="position: relative; z-index: 2;">
        <h3>Patient Information</h3>
        <p><strong>Name:</strong> {{patient.name}}</p>
        <p><strong>Age:</strong> {{patient.age}}</p>
    </div>
</div>
```

## React Component Example

```jsx
function ScenarioCard({ scenario, patient }) {
    const cardStyle = {
        position: 'relative',
        padding: '20px',
        borderRadius: '8px',
        backgroundColor: 'white',
        overflow: 'hidden',
    };

    const backgroundImageStyle = {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundImage: `url(${scenario.image})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        opacity: 0.3,
        zIndex: 0,
    };

    const gradientStyle = {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: `linear-gradient(
            to bottom,
            rgba(255, 255, 255, 0.9) 0%,
            rgba(255, 255, 255, 0.7) 30%,
            rgba(255, 255, 255, 0.5) 60%,
            rgba(255, 255, 255, 0.95) 100%
        )`,
        zIndex: 1,
    };

    const contentStyle = {
        position: 'relative',
        zIndex: 2,
    };

    return (
        <div style={cardStyle}>
            <div style={backgroundImageStyle} />
            <div style={gradientStyle} />
            <div style={contentStyle}>
                <h3>Patient Information</h3>
                <p><strong>Name:</strong> {patient.name}</p>
                <p><strong>Age:</strong> {patient.age}</p>
                <h3>Scenario</h3>
                <p>{scenario.description}</p>
            </div>
        </div>
    );
}
```

## Customization Options

### Adjust Gradient Strength
- Increase white opacity values (0.9 → 0.95) for stronger fade
- Decrease white opacity values (0.9 → 0.7) for more visible image

### Adjust Image Opacity
- Change `opacity: 0.3` to `0.2` for subtler background
- Change to `0.4` or `0.5` for more prominent background

### Gradient Direction
- `to bottom` - fade from top to bottom
- `to top` - fade from bottom to top
- `to right` - fade from left to right
- `to left` - fade from right to left

### Different Gradient Patterns
```css
/* Subtle fade from edges */
background: radial-gradient(
    ellipse at center,
    rgba(255, 255, 255, 0.9) 0%,
    rgba(255, 255, 255, 0.5) 70%,
    rgba(255, 255, 255, 0.95) 100%
);
```

## Notes

- The image URL comes from `scenario.image` field in your Firestore documents
- Make sure the image has proper CORS headers if hosting on Cloud Storage
- Test with different image sizes to ensure good coverage
- Consider adding `background-attachment: fixed` for parallax effect (optional)

