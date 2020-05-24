from flask import Flask, render_template, request
import pandas as pd
from bokeh.models import ColumnDataSource, LinearColorMapper
from bokeh.plotting import figure
from bokeh.transform import dodge
from bokeh.palettes import Spectral6, Spectral11
from bokeh.embed import components
from bokeh.sampledata.us_counties import data as county_data
from numpy import median

from . import state_mapping

STATE_ENDPOINT = "https://data.cdc.gov/resource/9bhg-hcku.json"
COUNTY_ENDPOINT = "https://data.cdc.gov/resource/kn79-hsxy.json"

DATE_COLS = ['data_as_of', 'start_week', 'end_week']

STATE_FIGURES = ['covid_19_deaths', 'total_deaths', 'pneumonia_deaths',
                 'pneumonia_and_covid_19_deaths', 'influenza_deaths',
                 'pneumonia_influenza_or_covid']

DIMS = ['sex', 'age_group']

AGE_GROUPS = ['Under 1 year', '1-4 years', '5-14 years', '15-24 years',
              '25-34 years', '35-44 years', '45-54 years', '55-64 years',
              '65-74 years', '75-84 years', '85 years and over']

app = Flask(__name__)


def deaths_by_county(data, state):

    try:
        def filter_state(mapped):
            if mapped:
                for k, v in mapped.items():
                    return k, v
            else:
                return
        mapped = {
            code: name for code, name in state_mapping.items() if name == f'{state}'
        }

        state_code, state_name = filter_state(mapped)

        df_state = data[data['state_name'] == state_code]
        df_state.drop(['data_as_of', 'start_week', 'end_week'], 1)

        counties = {
            code: county_name for code, county_name in county_data.items() if county_name['state'] == state_code.lower()
        }

        county_df = pd.DataFrame(counties.values())
        county_df['county_key'] = county_df['detailed name'].apply(lambda x: x.split(',')[0])
        df_merged = pd.merge(df_state, county_df, left_on='county_name', right_on="county_key", how='right')
        df_merged.fillna(0, inplace=True)
        df_merged.covid_death = df_merged.covid_death.astype(float)
        county_xs = df_merged.lons.values.tolist()
        county_ys = df_merged.lats.values.tolist()
        county_names = df_merged.name.values.tolist()
        county_rates = df_merged.covid_death.values.tolist()
        color_mapper = LinearColorMapper(palette=Spectral11,
                                         low=median(county_rates), high=max(county_rates))
        data = dict(
            x=county_xs,
            y=county_ys,
            name=county_names,
            rate=county_rates,
        )

        TOOLS = "pan,wheel_zoom,reset,hover,save"

        p = figure(
            title=f"{state_name} - Covid Deaths", tools=TOOLS,
            x_axis_location=None, y_axis_location=None,
            tooltips=[
                ("Name", "@name"), ("Total Deaths", "@rate"), ("(Long, Lat)", "($x, $y)")
            ]
        )

        p.grid.grid_line_color = None
        p.hover.point_policy = "follow_mouse"

        p.patches('x', 'y', source=data,
                  fill_color={'field': 'rate', 'transform': color_mapper},
                  fill_alpha=0.7, line_color="white", line_width=0.5)

        return p
    except Exception:
        return None,None


def age_by_state(data, state):
    df_state = data[data['state'] == f'{state}']
    df_state = df_state[df_state['age_group'].isin(AGE_GROUPS)]
    cohorts = df_state.age_group.unique()
    df_age = df_state.groupby('age_group')[STATE_FIGURES].sum()
    source = ColumnDataSource(data=df_age)
    plot = figure(x_range=cohorts,
                  plot_height=500,
                  plot_width=1000,
                  title=f"Deaths x Age - {state}",
                  toolbar_location="right", tools=["zoom_in", "zoom_out"])

    plot.vbar(x=dodge('age_group', -.25, range=plot.x_range),
              top="covid_19_deaths",
              width=.25,
              line_color="white",
              fill_color=Spectral11[-1],
              source=source,
              legend_label="Covid-19 Deaths")

    plot.vbar(x=dodge('age_group', 0, range=plot.x_range),
              top="pneumonia_deaths",
              width=.25,
              line_color="white",
              fill_color=Spectral11[8],
              source=source, legend_label="Pneumonia Deaths")

    plot.vbar(x=dodge('age_group', .25, range=plot.x_range),
              top="influenza_deaths",
              width=.25,
              line_color="white",
              fill_color=Spectral11[0],
              source=source, legend_label="Influenza Deaths")

    plot.xgrid.grid_line_color = None
    plot.xaxis.axis_label = "Age Bucket"
    plot.yaxis.axis_label = "Deaths"
    plot.y_range.start = 0

    plot.x_range.range_padding = None
    plot.xgrid.grid_line_color = None
    plot.legend.location = "top_left"
    plot.legend.orientation = "horizontal"
    return plot, df_age


@app.route('/')
def index():
    if request.args.get("state") is None:
        current_state = "New York"
    else:
        current_state = request.args.get("state")

    state_data = pd.read_json(STATE_ENDPOINT, convert_dates=DATE_COLS)
    county_data = pd.read_json(COUNTY_ENDPOINT)

    offset = state_data[state_data['state'].str.contains("Total")].index
    state_data.drop(offset, inplace=True)

    state_plot, df = age_by_state(state_data, current_state)
    county_plot = deaths_by_county(county_data, current_state)

    state_script, sate_div = components(state_plot)
    county_script, county_div = components(county_plot)

    states = state_data['state'].values
    states = list(filter(lambda  x: x != "New York City",states))
    return render_template("index.html", state_script=state_script, state_div=sate_div,
                           county_script=county_script, county_div=county_div,
                           current_state=current_state, states=states)
