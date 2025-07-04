# ================================================================================================================ #
# Import Statements

# Streamlit imports
import streamlit as st

# Pandas imports
import pandas as pd

# Ladybug imports
import ladybug.epw as epw
from ladybug.datacollection import HourlyContinuousCollection
from ladybug.sunpath import Sunpath
from ladybug_comfort.collection.pet import PET
from ladybug_comfort.collection.solarcal import OutdoorSolarCal

# Plotly imports
import plotly.graph_objects as go
import plotly.io as pio

# Other imports
import calendar
from io import StringIO
import tempfile



# ================================================================================================================ #
# Calculate the Annual PET Values


@st.cache_data
def load_epw_from_bytes(epw_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".epw") as tmp_file:
        tmp_file.write(epw_bytes)
        tmp_path = tmp_file.name
        return epw.EPW(tmp_path)



@st.cache_data
def calculate_pet(_epw_file, met, clo):

    # Load the epw data
    epw_data = (_epw_file)

    # Get the location and weather data
    location = epw_data.location
    temperature = epw_data.dry_bulb_temperature
    humidity = epw_data.relative_humidity
    wind = epw_data.wind_speed
    normal_rad = epw_data.direct_normal_radiation
    diffused_rad = epw_data.diffuse_horizontal_radiation
    horizontal_infra = epw_data.horizontal_infrared_radiation_intensity

    # Create a list of 0 wind values
    wind_header = wind.header
    zero_wind = HourlyContinuousCollection(wind_header, [0]*8760)

    # Create a list of 0 normal radiation values
    normal_rad_header = normal_rad.header
    zero_normal_rad = HourlyContinuousCollection(normal_rad_header, [0]*8760)

    # Create a list of 0 diffused radiation values
    diffused_rad_header = diffused_rad.header
    zero_diffused_rad = HourlyContinuousCollection(diffused_rad_header, [0]*8760)

    # Create a list of 0 horizontal infrared radiation values
    horizontal_infra_header = horizontal_infra.header
    zero_horizontal_infra = HourlyContinuousCollection(horizontal_infra_header, [0]*8760)

    # ---------------------------------------------------------- #

    # Calculate the two MRTs
    exposed_mrt = OutdoorSolarCal(location, normal_rad, diffused_rad, horizontal_infra, temperature, fraction_body_exposed = 1, sky_exposure = 1).mean_radiant_temperature
    sheltered_mrt = OutdoorSolarCal(location, zero_normal_rad, zero_diffused_rad, horizontal_infra, temperature, fraction_body_exposed = 1, sky_exposure = 1).mean_radiant_temperature


    # Calculate the PET values for different conditions
    fully_exposed = PET(temperature, humidity, exposed_mrt, wind, met_rate=met, clo_value=clo)
    sun_sheltered = PET(temperature, humidity, sheltered_mrt, wind, met_rate=met, clo_value=clo)
    wind_sheltered = PET(temperature, humidity, exposed_mrt, zero_wind, met_rate=met, clo_value=clo)
    fully_sheltered = PET(temperature, humidity, sheltered_mrt, zero_wind, met_rate=met, clo_value=clo)

    # Get the PET categories for each condition
    fully_exposed_category = fully_exposed.pet_category.values
    sun_sheltered_category = sun_sheltered.pet_category.values
    wind_sheltered_category = wind_sheltered.pet_category.values
    fully_sheltered_category = fully_sheltered.pet_category.values     

    # Get the PET values for each condition
    fully_exposed_pet = fully_exposed.physiologic_equivalent_temperature.values
    sun_sheltered_pet = sun_sheltered.physiologic_equivalent_temperature.values
    wind_sheltered_pet = wind_sheltered.physiologic_equivalent_temperature.values
    fully_sheltered_pet = fully_sheltered.physiologic_equivalent_temperature.values

    # Assuming your DataFrame is named df and has 8760 rows
    start_date = '2025-01-01 00:00'
    end_date = '2025-12-31 23:00'
    datetime_range = pd.date_range(start=start_date, end=end_date, freq='h')

    # Create the sun path
    sp = Sunpath.from_location(location)

    # Calculate sun up boolean for each hour of the year
    sun_up = []

    for i in range(0, 8760):
        sun = sp.calculate_sun_from_hoy(i).is_during_day
        sun_up.append(sun)

    df = pd.DataFrame({
        'Date' : datetime_range,
        'Sun' : sun_up,
        'Fully Exposed PET': fully_exposed_pet,
        'Sun Sheltered PET': sun_sheltered_pet,
        'Wind Sheltered PET': wind_sheltered_pet,
        'Fully Sheltered PET': fully_sheltered_pet,
        'Fully Exposed Category': fully_exposed_category,
        'Sun Sheltered Category': sun_sheltered_category,
        'Wind Sheltered Category': wind_sheltered_category,
        'Fully Sheltered Category': fully_sheltered_category
    })

    # Mapping dictionary
    temp_map = {
        -4: 'Very Cold',
        -3: 'Cold',
        -2: 'Cool',
        -1: 'Slightly Cool',
        0: 'Comfort',
        1: 'Slightly Warm',
        2: 'Warm',
        3: 'Hot',
        4: 'Very Hot'
    }

    # Replace the integers with category names
    comfort_column_names = ['Fully Exposed Category', 'Sun Sheltered Category', 'Wind Sheltered Category', 'Fully Sheltered Category']

    # Apply the mapping
    df[comfort_column_names] = df[comfort_column_names].replace(temp_map)
    
    return df


# ================================================================================================================ #
# Calculate the Monthly Percentages

def calculate_monthly_comfort_percentages(df, category_column, month_column='Month', comfort_categories=None):

    # Group and count occurrences
    monthly_data = df.groupby(month_column)[category_column].value_counts().unstack().fillna(0)

    # Normalize to percentage
    monthly_percentages = monthly_data.div(monthly_data.sum(axis=1), axis=0) * 100

    # Ensure all categories are present
    if comfort_categories:
        for cat in comfort_categories:
            if cat not in monthly_percentages.columns:
                monthly_percentages[cat] = 0
        monthly_percentages = monthly_percentages[comfort_categories]

    # Reorder months: Dec to Nov
    custom_month_order = [12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    monthly_percentages = monthly_percentages.reindex(custom_month_order)

    # Convert numeric index to month abbreviations
    monthly_percentages['Month'] = [calendar.month_abbr[m] for m in monthly_percentages.index]

    return monthly_percentages


# ================================================================================================================ #
# Make the temp chart

def create_temp_bar_chart(monthly_comfort):

    # Create stacked bar chart using plotly.go
    fig = go.Figure()

    threshold = 10  # percent

    label_cats = ["Comfort", 'Slightly Cool', "Slightly Warm"]

    comfort_colors = {
    'Very Cold': "#456E95",
    'Cold': "#85BBE1",
    'Cool': "#A9C9E5",
    'Slightly Cool': "#D9E7F5",
    'Comfort': "#60B22E",
    'Slightly Warm': "#F0CBC9",
    'Warm': "#E7A4A5",
    'Hot': "#E07777",
    'Very Hot': "#971E1E"
    }

    for cat in comfort_categories:
        y_vals = monthly_comfort[cat]
        x_vals = [calendar.month_abbr[m] for m in monthly_comfort.index]

        # Only show labels if the value > 20%
        text_labels = [f"{val:.0f}%" if (val > threshold and cat in label_cats) else "" for val in y_vals]

        fig.add_trace(go.Bar(
            x=x_vals,
            y=y_vals,
            name=cat,
            marker_color=comfort_colors[cat],
            text=text_labels,
            textposition="inside",  # Or "auto", "outside"
            insidetextanchor="middle",
            textfont=dict(color="rgba(255, 255, 255, 0.8)", size=9),  # Optional: better visibility
            showlegend=False  # Keep this if you're handling the legend separately
        ))

    fig.update_layout(
        barmode='stack',
        bargap = (0.1),
        margin=dict(t=10, b=30, l=50, r=0.1),
        title=None,
        xaxis_title=None,
        yaxis_title='Percentage of Time (%)')

    return fig


# ================================================================================================================ #
# Make the donut chart

def create_comfort_donut_chart(df, category_column):
    # Count occurrences of each label
    label_counts = df[category_column].value_counts().sort_values(ascending=False)

    # Define custom order
    ordered_labels = [
        "Very Cold", "Cold", "Cool", "Slightly Cool",
        "Comfort", "Slightly Warm", "Warm", "Hot", "Very Hot"
    ]

    # Reindex to match order (fill missing with 0)
    label_counts = label_counts.reindex(ordered_labels, fill_value=0)

    # Custom color dictionary
    comfort_colors = {
        "Very Cold": "#456E95",
        "Cold": "#85BBE1",
        "Cool": "#A9C9E5",
        "Slightly Cool": "#D9E7F5",
        "Comfort": "#60B22E",
        "Slightly Warm": "#F0CBC9",
        "Warm": "#E7A4A5",
        "Hot": "#E07777",
        "Very Hot": "#971E1E"
    }

    # Map labels to colors
    colors = [comfort_colors[label] for label in label_counts.index]

    # Create donut chart
    fig = go.Figure(data=[go.Pie(
        labels=label_counts.index,
        values=label_counts.values,
        sort=False,
        direction='clockwise',
        rotation=0,
        hole=0.6,
        textinfo='percent',
        textposition='inside',
        marker=dict(colors=colors, line=dict(color='white', width=2))
    )])

    fig.update_layout(
        template='plotly_white',
          annotations=[dict(
              text='Annual<br>PET',
              x=0.5, y=0.5,
              font_size=20,
              showarrow=False,
              font_color='black',
              align='center'
              )],
        margin=dict(t=0.1, b=0.1, l=0.1, r=10),
        showlegend=False
        )

    return fig


# ================================================================================================================ #
# Page layout and title

# Make the page take up the whole width
st.set_page_config(layout="wide")

# Set the title
st.title("Outdoor Thermal Comfort")

# ================================================================================================================ #
# INPUT PARAMETERS

st.header("1. Weather Data and Human Parameters")

# Create three columns for the first section
import_col, human_col = st.columns([1, 3], gap='small', border=True)

# Set the column headers
import_col.subheader('Import Data')


# Upload EPW file
uploaded_file = import_col.file_uploader("Upload an EPW file", type=["epw"])

if uploaded_file is not None:
    epw_data = load_epw_from_bytes(uploaded_file.getvalue())


# Create the first section
human_col.subheader("Set the Human Parameters")
met = human_col.number_input('Set the Metabolic Rate (met)', value = 1.0)
clo = human_col.number_input('Set the Clothing Insulation (clo)', value = 1.0)


# ================================================================================================================ #
# INPUT PARAMETERS

st.header("2. PET Results")

# Create two columns for the second section
environment_col, temp_results_col = st.columns([1, 3], gap='small', border=True)

# Add the section header
environment_col.subheader("Conditions")

# Create the select box for the time of day
time_selection = environment_col.selectbox(
    "Filter the Time of the Day",
    ("Daytime", "Nighttime", 'Entire Day')
),

# Create the selct box for the comfort strategy selection
strategy_selection = environment_col.selectbox(
    'Comfort Strategy',
    ('Fully Exposed Category', 'Sun Sheltered Category', 'Wind Sheltered Category', 'Fully Sheltered Category')
)


# Add the section header
environment_col.subheader("Legend")



# Add the section header for the results
temp_results_col.subheader("Monthly and Annual Graphs")   

# Create the two columns for the results
temp_bar_col, temp_pie_col = temp_results_col.columns([3,1], gap='large', border=False)


# Define the comfort categories and their associated colors
comfort_colors = {
    "Very Hot": "#971E1E",
    "Hot": "#E07777",
    "Warm": "#E7A4A5",
    "Slightly Warm": "#F0CBC9",
    "Comfort": "#60B22E",
    "Slightly Cool": "#D9E7F5",
    "Cool": "#A9C9E5",
    "Cold": "#85BBE1",
    "Very Cold": "#456E95"
}


# ================================================================================================================ #

# EPW file path
# file_path = r'C:\Users\pehvert\OneDrive - Foster + Partners\Documents\03_Projects\PET_Dashboard\01_Data\SAU_RI_Riyadh-Khalid.Intl.AP.404370_TMYx.epw'

if 'epw_data' in locals() and epw_data is not None:
    # Calculate the PET values
    pet_df = calculate_pet(epw_data, met, clo)

    # Add the month for grouping
    pet_df['Month'] = pet_df['Date'].dt.month

    # Separate day and night pet DataFrames
    day_pet_df = pet_df[pet_df['Sun'] == True].copy()
    night_pet_df = pet_df[pet_df['Sun'] == False].copy()

    # Add the ideal strategy column for day PET
    day_pet_columns = ['Fully Exposed PET', 'Sun Sheltered PET', 'Wind Sheltered PET', 'Fully Sheltered PET']
    day_pet_df['Ideal Strategy'] = day_pet_df[day_pet_columns].apply(lambda row: row.sub(20.5).abs().idxmin(), axis=1)

    # Add the ideal strategy column for night PET
    night_pet_columns = ['Fully Exposed PET', 'Wind Sheltered PET']
    night_pet_df['Ideal Strategy'] = night_pet_df[day_pet_columns].apply(lambda row: row.sub(20.5).abs().idxmin(), axis=1)

    # Define comfort categories and colors
    comfort_categories = ['Very Cold', 'Cold', 'Cool', 'Slightly Cool', 'Comfort', 
                        'Slightly Warm', 'Warm', 'Hot', 'Very Hot']


    # Select the appropriate DataFrame based on the time selection
    if time_selection[0] == 'Daytime':
        data_df = day_pet_df

    elif time_selection[0] == 'Nighttime':
        data_df = night_pet_df


    # Calculate the monthly comfort percentages based on the selected strategy
    monthly_comfort = calculate_monthly_comfort_percentages(
        df = data_df,
        category_column = strategy_selection,
        comfort_categories = comfort_categories
    )

    # Create the bar chart and pie chart for the monthly comfort percentages
    temp_bar_fig = create_temp_bar_chart(monthly_comfort)

    # Create the donut chart for the comfort categories
    temp_pie_fig = create_comfort_donut_chart(data_df, category_column=strategy_selection)

    # Display the charts in the respective columns
    temp_bar_col.plotly_chart(temp_bar_fig, theme=None, use_container_width=True)
    temp_pie_col.plotly_chart(temp_pie_fig, theme=None, use_container_width=True)

# ================================================================================================================ #
st.header("4. Ideal Environmental Strategy")

