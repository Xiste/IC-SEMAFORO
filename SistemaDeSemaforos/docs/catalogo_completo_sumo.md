# Catálogo completo do SUMO instalado

Eclipse SUMO sumo 1.27.1

462 opções CLI. Gerado com scripts/exportar_catalogos.py, sem depender de um template XML estático.

[CSV integral](catalogos/sumo_options.csv). As descrições originais e padrões vêm do executável instalado.
Atributos de rede/vType e outras ferramentas possuem catálogos próprios.

## Arquivos de configuração (configuration)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| configuration-file | FILE |  | Loads the named config on startup |
| save-configuration | FILE |  | Saves current configuration into FILE |
| save-configuration.relative | BOOL | false | Enforce relative paths when saving the configuration |
| save-template | FILE |  | Saves a configuration template (empty) into FILE |
| save-schema | FILE |  | Saves the configuration schema into FILE |
| save-commented | BOOL |  | Adds comments to saved template, configuration, or schema |

## Arquivos de entrada (input)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| net-file | FILE |  | Load road network description from FILE |
| route-files | FILE |  | Load routes descriptions from FILE(s) |
| additional-files | FILE |  | Load further descriptions from FILE(s) |
| weight-files | FILE |  | Load edge/lane weights for online rerouting from FILE |
| weight-attribute | STR | traveltime | Name of the xml attribute which gives the edge weight |
| load-state | FILE |  | Loads a network state from FILE |
| load-state.offset | TIME | 0 | Shifts all times loaded from a saved state by the given offset |
| load-state.remove-vehicles | STR[] |  | Removes vehicles with the given IDs from the loaded state |
| junction-taz | BOOL | false | Initialize a TAZ for every junction to use attributes toJunction and fromJunction |

## Arquivos e métricas de saída (output)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| write-license | BOOL | false | Include license info into every output file |
| write-metadata | BOOL | false | Write parsable metadata (configuration etc.) instead of comments |
| output-prefix | STR |  | Prefix which is applied to all output files. The special string &apos;TIME&apos; is replaced by the current time. |
| output-suffix | STR |  | Suffix which is applied to all output files. The special string &apos;TIME&apos; is replaced by the current time. |
| precision | INT | 2 | Defines the number of digits after the comma for floating point output |
| precision.geo | INT | 6 | Defines the number of digits after the comma for lon,lat output |
| output.compression | STR |  | Defines the standard compression algorithm (currently only for parquet output) |
| output.format | STR | xml | Defines the standard output format if not derivable from the file name (&apos;xml&apos;, &apos;csv&apos;, &apos;parquet&apos;) |
| output.column-header | STR | tag | How to derive column headers from attribute names (&apos;none&apos;, &apos;tag&apos;, &apos;auto&apos;, &apos;plain&apos;) |
| output.column-separator | STR | ; | Separator in CSV output |
| human-readable-time | BOOL | false | Write time values as hour:minute:second or day:hour:minute:second rather than seconds |
| netstate-dump | FILE |  | Save complete network states into FILE |
| netstate-dump.empty-edges | BOOL | false | Write also empty edges completely when dumping |
| netstate-dump.precision | INT | 2 | Write positions and speeds with the given precision (default 2) |
| emission-output | FILE |  | Save the emission values of each vehicle |
| emission-output.precision | INT | 2 | Write emission values with the given precision (default 2) |
| emission-output.geo | BOOL | false | Save the positions in emission output using geo-coordinates (lon/lat) |
| emission-output.step-scaled | BOOL | false | Write emission values scaled to the step length rather than as per-second values |
| emission-output.attributes | STR[] |  | List attributes that should be included in the emission output |
| battery-output | FILE |  | Save the battery values of each vehicle |
| battery-output.precision | INT | 2 | Write battery values with the given precision (default 2) |
| elechybrid-output | FILE |  | Save the elecHybrid values of each vehicle |
| elechybrid-output.precision | INT | 2 | Write elecHybrid values with the given precision (default 2) |
| elechybrid-output.aggregated | BOOL | false | Write elecHybrid values into one aggregated file |
| chargingstations-output | FILE |  | Write data of charging stations |
| chargingstations-output.aggregated | BOOL | false | Write aggregated charging event data instead of single time steps |
| chargingstations-output.aggregated.write-unfinished | BOOL | false | Write aggregated charging event data for vehicles which have not arrived at simulation end |
| overheadwiresegments-output | FILE |  | Write data of overhead wire segments |
| substations-output | FILE |  | Write data of electrical substation stations |
| substations-output.precision | INT | 2 | Write substation values with the given precision (default 2) |
| fcd-output | FILE |  | Save the Floating Car Data |
| fcd-output.geo | BOOL | false | Save the Floating Car Data using geo-coordinates (lon/lat) |
| fcd-output.utm | BOOL | false | Save the Floating Car Data using utm/unshifted coordinates (x/y) |
| fcd-output.signals | BOOL | false | Add the vehicle signal state to the FCD output (brake lights etc.) |
| fcd-output.distance | BOOL | false | Add kilometrage to the FCD output (linear referencing) |
| fcd-output.acceleration | BOOL | false | Add acceleration to the FCD output |
| fcd-output.speed-relative | BOOL | false | Add relative speed (vehicle speed / edge speed limit) to the FCD output |
| fcd-output.max-leader-distance | FLOAT | -1 | Add leader vehicle information to the FCD output (within the given distance) |
| fcd-output.params | STR[] |  | Add generic parameter values to the FCD output |
| fcd-output.filter-edges.input-file | FILE |  | Restrict fcd output to the edge selection from the given input file |
| fcd-output.attributes | STR[] |  | List attributes that should be included in the FCD output |
| fcd-output.filter-shapes | STR[] |  | List shape names that should be used to filter the FCD output |
| fcd-output.skip-empty | BOOL | false | Do not save data for time steps which have no vehicles / transportables |
| person-fcd-output | FILE |  | Save fcd for persons and container to separate FILE |
| device.ssm.filter-edges.input-file | FILE |  | Restrict SSM device output to the edge selection from the given input file |
| full-output | FILE |  | Save a lot of information for each timestep (very redundant) |
| queue-output | FILE |  | Save the vehicle queues at the junctions (experimental) |
| queue-output.period | TIME | -1 | Save vehicle queues with the given period |
| vtk-output | FILE |  | Save complete vehicle positions inclusive speed values in the VTK Format (usage: /path/out will produce /path/out_$TIMESTEP$.vtp files) |
| amitran-output | FILE |  | Save the vehicle trajectories in the Amitran format |
| summary-output | FILE |  | Save aggregated vehicle departure info into FILE |
| summary-output.period | TIME | -1 | Save summary-output with the given period |
| person-summary-output | FILE |  | Save aggregated person counts into FILE |
| tripinfo-output | FILE |  | Save single vehicle trip info into FILE |
| tripinfo-output.write-unfinished | BOOL | false | Write tripinfo output for vehicles which have not arrived at simulation end |
| tripinfo-output.write-undeparted | BOOL | false | Write tripinfo output for vehicles which have not departed at simulation end because of depart delay |
| personinfo-output | FILE |  | Save personinfo and containerinfo to separate FILE |
| vehroute-output | FILE |  | Save single vehicle route info into FILE |
| vehroute-output.exit-times | BOOL | false | Write the exit times for all edges |
| vehroute-output.last-route | BOOL | false | Write the last route only |
| vehroute-output.sorted | BOOL | false | Sorts the output by departure time |
| vehroute-output.dua | BOOL | false | Write the output in the duarouter alternatives style |
| vehroute-output.cost | BOOL | false | Write costs for all routes |
| vehroute-output.intended-depart | BOOL | false | Write the output with the intended instead of the real departure time |
| vehroute-output.route-length | BOOL | false | Include total route length in the output |
| vehroute-output.write-unfinished | BOOL | false | Write vehroute output for vehicles which have not arrived at simulation end |
| vehroute-output.skip-ptlines | BOOL | false | Skip vehroute output for public transport vehicles |
| vehroute-output.incomplete | BOOL | false | Include invalid routes and route stubs in vehroute output |
| vehroute-output.stop-edges | BOOL | false | Include information about edges between stops |
| vehroute-output.speedfactor | BOOL | false | Write the vehicle speedFactor (defaults to &apos;true&apos; if departSpeed is written) |
| vehroute-output.internal | BOOL | false | Include internal edges in the output |
| personroute-output | FILE |  | Save person and container routes to separate FILE |
| link-output | FILE |  | Save links states into FILE |
| railsignal-block-output | FILE |  | Save railsignal-blocks into FILE |
| railsignal-vehicle-output | FILE |  | Record entry and exit times of vehicles for railsignal blocks into FILE |
| bt-output | FILE |  | Save bluetooth visibilities into FILE (in conjunction with device.btreceiver and device.btsender) |
| lanechange-output | FILE |  | Record lane changes and their motivations for all vehicles into FILE |
| lanechange-output.started | BOOL | false | Record start of lane change manoeuvres |
| lanechange-output.ended | BOOL | false | Record end of lane change manoeuvres |
| lanechange-output.xy | BOOL | false | Record coordinates of lane change manoeuvres |
| stop-output | FILE |  | Record stops and loading/unloading of passenger and containers for all vehicles into FILE |
| stop-output.write-unfinished | BOOL | false | Write stop output for stops which have not ended at simulation end |
| collision-output | FILE |  | Write collision information into FILE |
| edgedata-output | FILE |  | Write aggregated traffic statistics for all edges into FILE |
| lanedata-output | FILE |  | Write aggregated traffic statistics for all lanes into FILE |
| statistic-output | FILE |  | Write overall statistics into FILE |
| deadlock-output | FILE |  | Write reports on deadlocks FILE |
| save-state.times | STR[] |  | Use TIME[] as times at which a network state written |
| save-state.period | TIME | -1 | save state repeatedly after TIME period |
| save-state.period.keep | INT | 0 | Keep only the last INT periodic state files |
| save-state.prefix | FILE | state | Prefix for network states |
| save-state.suffix | STR | .xml.gz | Suffix for network states (.xml.gz or .xml) |
| save-state.files | FILE |  | Files for network states |
| save-state.rng | BOOL | false | Save random number generator states |
| save-state.transportables | BOOL | false | Save person and container states (experimental) |
| save-state.constraints | BOOL | false | Save rail signal constraints |
| save-state.precision | INT | 2 | Write internal state values with the given precision (default 2) |

## Tempo da simulação (time)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| begin | TIME | 0 | Defines the begin time in seconds; The simulation starts at this time |
| end | TIME | -1 | Defines the end time in seconds; The simulation ends at this time |
| step-length | TIME | 1 | Defines the step duration in seconds |

## Processamento e comportamento da simulação (processing)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| step-method.ballistic | BOOL | false | Whether to use ballistic method for the positional update of vehicles (default is a semi-implicit Euler method). |
| extrapolate-departpos | BOOL | false | Whether vehicles that depart between simulation steps should extrapolate the depart position |
| threads | INT | 1 | Defines the number of threads for parallel simulation |
| lateral-resolution | FLOAT | -1 | Defines the resolution in m when handling lateral positioning within a lane (with -1 all vehicles drive at the center of their lane |
| route-steps | TIME | 200 | Load routes for the next number of seconds ahead |
| no-internal-links | BOOL | false | Disable (junction) internal links |
| ignore-junction-blocker | TIME | -1 | Ignore vehicles which block the junction after they have been standing for SECONDS (-1 means never ignore) |
| ignore-route-errors | BOOL | false | Do not check whether routes are connected |
| ignore-accidents | BOOL | false | Do not check whether accidents occur |
| collision.action | STR | teleport | How to deal with collisions: [none,warn,teleport,remove] |
| intermodal-collision.action | STR | warn | How to deal with collisions between vehicle and pedestrian: [none,warn,teleport,remove] |
| collision.stoptime | TIME | 0 | Let vehicle stop for TIME before performing collision.action (except for action &apos;none&apos;) |
| intermodal-collision.stoptime | TIME | 0 | Let vehicle stop for TIME before performing intermodal-collision.action (except for action &apos;none&apos;) |
| collision.check-junctions | BOOL | false | Enables collisions checks on junctions |
| collision.check-junctions.mingap | FLOAT | 0 | Increase or decrease sensitivity for junction collision check |
| collision.mingap-factor | FLOAT | -1 | Sets the fraction of minGap that must be maintained to avoid collision detection. If a negative value is given, the carFollowModel parameter is used |
| keep-after-arrival | TIME | 0 | After a vehicle arrives, keep it in memory for the given TIME (for TraCI access) |
| max-num-vehicles | INT | -1 | Delay vehicle insertion to stay within the given maximum number |
| max-num-persons | INT | -1 | Delay person insertion to stay within the given maximum number |
| max-num-teleports | INT | -1 | Abort the simulation if the given maximum number of teleports is exceeded |
| scale | FLOAT | 1 | Scale demand by the given factor (by discarding or duplicating vehicles) |
| scale-suffix | STR | . | Suffix to be added when creating ids for cloned vehicles |
| time-to-teleport | TIME | 300 | Specify how long a vehicle may wait until being teleported, defaults to 300, non-positive values disable teleporting |
| time-to-teleport.highways | TIME | 0 | The waiting time after which vehicles on a fast road (speed &gt; 69km/h) are teleported if they are on a non-continuing lane |
| time-to-teleport.highways.min-speed | FLOAT | 19.1667 | The waiting time after which vehicles on a fast road (default: speed &gt; 69km/h) are teleported if they are on a non-continuing lane |
| time-to-teleport.disconnected | TIME | -1 | The waiting time after which vehicles with a disconnected route are teleported. Negative values disable teleporting |
| time-to-teleport.remove | BOOL | false | Whether vehicles shall be removed after waiting too long instead of being teleported |
| time-to-teleport.remove-constraint | BOOL | false | Whether rail-signal-constraint based deadlocks shall be cleared by removing a constraint |
| time-to-teleport.ride | TIME | -1 | The waiting time after which persons / containers waiting for a pickup are teleported. Negative values disable teleporting |
| time-to-teleport.bidi | TIME | -1 | The waiting time after which vehicles on bidirectional edges are teleported |
| time-to-teleport.railsignal-deadlock | TIME | -1 | The waiting time after which vehicles in a rail-signal based deadlock are teleported |
| waiting-time-memory | TIME | 100 | Length of time interval, over which accumulated waiting time is taken into account (default is 100s.) |
| startup-wait-threshold | TIME | 2 | Minimum consecutive waiting time before applying startupDelay |
| max-depart-delay | TIME | -1 | How long vehicles wait for departure before being skipped, defaults to -1 which means vehicles are never skipped |
| sloppy-insert | BOOL | false | Whether insertion on an edge shall not be repeated in same step once failed |
| eager-insert | BOOL | false | Whether each vehicle is checked separately for insertion on an edge |
| emergency-insert | BOOL | false | Allow inserting a vehicle in a situation which requires emergency braking |
| insertion-checks | STR | all | Override default value for vehicle attribute insertionChecks |
| random-depart-offset | TIME | 0 | Each vehicle receives a random offset to its depart value drawn uniformly from [0, TIME] |
| lanechange.duration | TIME | 0 | Duration of a lane change maneuver (default 0) |
| lanechange.overtake-right | BOOL | false | Whether overtaking on the right on motorways is permitted |
| tls.all-off | BOOL | false | Switches off all traffic lights. |
| tls.actuated.show-detectors | BOOL | false | Sets default visibility for actuation detectors |
| tls.actuated.jam-threshold | FLOAT | -1 | Sets default jam-threshold parameter for all actuation detectors |
| tls.actuated.detector-length | FLOAT | 0 | Sets default detector length parameter for all actuation detectors |
| tls.delay_based.detector-range | FLOAT | 100 | Sets default range for detecting delayed vehicles |
| tls.yellow.min-decel | FLOAT | 3 | Minimum deceleration when braking at yellow |
| railsignal-moving-block | BOOL | false | Let railsignals operate in moving-block mode by default |
| railsignal.moving-block.default-classes | STR[] | tram,cable_car | List vehicle classes that default to moving-block operations |
| railsignal.moving-block.max-dist | FLOAT | 200 | Maximum signal distance above which zipper conflicts are ignored |
| railsignal.max-block-length | FLOAT | 20000 | Do not build blocks longer than FLOAT and issue a warning instead |
| railsignal.default-classes | STR[] | rail,rail_fast,rail_electric,rail_urban,subway | List vehicle classes that uses block-based insertion checks even when the network has no rail signals for them |
| time-to-impatience | TIME | 180 | Specify how long a vehicle may wait until impatience grows from 0 to 1, defaults to 300, non-positive values disable impatience growth |
| default.departspeed | STR | avg | Select default depart speed |
| default.departlane | STR | best_prob | Select default depart lane |
| default.action-step-length | FLOAT | 0 | Length of the default interval length between action points for the car-following and lane-change models (in seconds). If not specified, the simulation step-length is used per default. Vehicle- or VType-specific settings override the default. Must be a multiple of the simulation step-length. |
| default.carfollowmodel | STR | Krauss | Select default car following model (Krauss, IDM, ...) |
| default.speeddev | FLOAT | -1 | Select default speed deviation. A negative value implies vClass specific defaults (0.1 for the default passenger class) |
| default.emergencydecel | STR | default | Select default emergencyDecel value among (&apos;decel&apos;, &apos;default&apos;, FLOAT) which sets the value either to the same as the deceleration value, a vClass-class specific default or the given FLOAT in m/s^2 |
| overhead-wire.solver | BOOL | true | Use Kirchhoff&apos;s laws for solving overhead wire circuit |
| overhead-wire.recuperation | BOOL | true | Enable recuperation from the vehicle equipped with elecHybrid device into the overhead wire. |
| overhead-wire.substation-current-limits | BOOL | true | Enable current limits of traction substation during solving the overhead wire electrical circuit. |
| emergencydecel.warning-threshold | FLOAT | 1 | Sets the fraction of emergency decel capability that must be used to trigger a warning. |
| parking.maneuver | BOOL | false | Whether parking simulation includes maneuvering time and associated lane blocking |
| use-stop-ended | BOOL | false | Override stop until times with stop ended times when given |
| use-stop-started | BOOL | false | Override stop arrival times with stop started times when given |
| pedestrian.model | STR | striping | Select among pedestrian models [&apos;nonInteracting&apos;, &apos;striping&apos;, &apos;jupedsim&apos;, &apos;remote&apos;] |
| pedestrian.timegap-crossing | FLOAT | 2 | Minimal acceptable gap (in seconds) between two vehicles before starting to cross |
| pedestrian.striping.stripe-width | FLOAT | 0.64 | Width of parallel stripes for segmenting a sidewalk (meters) for use with model &apos;striping&apos; |
| pedestrian.striping.dawdling | FLOAT | 0.2 | Factor for random slow-downs [0,1] for use with model &apos;striping&apos; |
| pedestrian.striping.mingap-to-vehicle | FLOAT | 0.25 | Minimal gap / safety buffer (in meters) from a pedestrian to another vehicle for use with model &apos;striping&apos; |
| pedestrian.striping.jamtime | TIME | 300 | Time in seconds after which pedestrians start squeezing through a jam when using model &apos;striping&apos; (non-positive values disable squeezing) |
| pedestrian.striping.jamtime.crossing | TIME | 10 | Time in seconds after which pedestrians start squeezing through a jam while on a pedestrian crossing when using model &apos;striping&apos; (non-positive values disable squeezing) |
| pedestrian.striping.jamtime.narrow | TIME | 1 | Time in seconds after which pedestrians start squeezing through a jam while on a narrow lane when using model &apos;striping&apos; |
| pedestrian.striping.jamfactor | FLOAT | 0.25 | Factor for reducing speed of pedestrian in jammed state |
| pedestrian.striping.reserve-oncoming | FLOAT | 0 | Fraction of stripes to reserve for oncoming pedestrians |
| pedestrian.striping.reserve-oncoming.junctions | FLOAT | 0.34 | Fraction of stripes to reserve for oncoming pedestrians on crossings and walkingareas |
| pedestrian.striping.reserve-oncoming.max | FLOAT | 1.28 | Maximum width in m to reserve for oncoming pedestrians |
| pedestrian.striping.legacy-departposlat | BOOL | false | Interpret departPosLat for walks in legacy style |
| pedestrian.striping.walkingarea-detail | INT | 4 | Generate INT intermediate points to smooth out lanes within the walkingarea |
| ride.stop-tolerance | FLOAT | 10 | Tolerance to apply when matching pedestrian and vehicle positions on boarding at individual stops |
| mapmatch.distance | FLOAT | 100 | Maximum distance when mapping input coordinates (fromXY etc.) to the road network |
| mapmatch.junctions | BOOL | false | Match positions to junctions instead of edges |
| mapmatch.taz | BOOL | false | Match positions to taz instead of edges |
| weights.turnaround-penalty | FLOAT | 5 | Apply the given time penalty when computing routing costs for turnaround internal lanes |
| weights.reversal-penalty | FLOAT | 60 | Apply the given time penalty when computing routing costs for train reversal. Negative values disable reversal |
| persontrip.walk-opposite-factor | FLOAT | 1 | Use FLOAT as a factor on walking speed against vehicle traffic direction |

## Cálculo de rotas (routing)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| routing-algorithm | STR | dijkstra | Select among routing algorithms [&apos;dijkstra&apos;, &apos;astar&apos;, &apos;CH&apos;, &apos;CHWrapper&apos;] |
| weights.random-factor | FLOAT | 1 | Edge weights for routing are dynamically disturbed by a random factor drawn uniformly from [1,FLOAT) |
| weights.random-factor.dynamic | BOOL | false | When using option --weights.random-factor, vary the randomness over time |
| weights.minor-penalty | FLOAT | 1.5 | Apply the given time penalty when computing minimum routing costs for minor-link internal lanes |
| weights.tls-penalty | FLOAT | 0 | Apply scaled travel time penalties based on green split when computing minimum routing costs for internal lanes at traffic lights |
| weights.priority-factor | FLOAT | 0 | Consider edge priorities in addition to travel times, weighted by factor |
| weights.separate-turns | FLOAT | 0 | Distinguish travel time by turn direction and shift a fraction of the estimated time loss ahead of the intersection onto the internal edges |
| astar.all-distances | FILE |  | Initialize lookup table for astar from the given file (generated by marouter --all-pairs-output) |
| astar.landmark-distances | FILE |  | Initialize lookup table for astar ALT-variant from the given file |
| persontrip.walkfactor | FLOAT | 0.75 | Use FLOAT as a factor on pedestrian maximum speed during intermodal routing |
| persontrip.transfer.car-walk | STR[] | parkingAreas | Where are mode changes from car to walking allowed (possible values: &apos;parkingAreas&apos;, &apos;ptStops&apos;, &apos;allJunctions&apos; and combinations) |
| persontrip.transfer.taxi-walk | STR[] |  | Where taxis can drop off customers (&apos;allJunctions, &apos;ptStops&apos;, &apos;parkingAreas&apos;) |
| persontrip.transfer.walk-taxi | STR[] |  | Where taxis can pick up customers (&apos;allJunctions, &apos;ptStops&apos;, &apos;parkingAreas&apos;) |
| persontrip.default.group | STR |  | When set, trips between the same origin and destination will share a taxi by default |
| persontrip.taxi.waiting-time | TIME | 300 | Estimated time for taxi pickup |
| persontrip.ride-public-line | BOOL | false | Only use the intended public transport line rather than any alternative line that stops at the destination |
| railway.max-train-length | FLOAT | 1000 | Use FLOAT as a maximum train length when initializing the railway router |
| replay-rerouting | BOOL | false | Replay exact rerouting sequence from vehroute-output |
| device.rerouting.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;rerouting&apos; device |
| device.rerouting.explicit | STR[] |  | Assign a &apos;rerouting&apos; device to named vehicles |
| device.rerouting.deterministic | BOOL | false | The &apos;rerouting&apos; devices are set deterministic using a fraction of 1000 |
| device.rerouting.period | TIME | 0 | The period with which the vehicle shall be rerouted |
| device.rerouting.pre-period | TIME | 60 | The rerouting period before depart |
| device.rerouting.adaptation-weight | FLOAT | 0 | The weight of prior edge weights for exponential moving average |
| device.rerouting.adaptation-steps | INT | 180 | The number of steps for moving average weight of prior edge weights |
| device.rerouting.adaptation-interval | TIME | 1 | The interval for updating the edge weights |
| device.rerouting.threshold.factor | FLOAT | 1 | Only reroute if the new route is faster than the current route by the given factor |
| device.rerouting.threshold.constant | TIME | 0 | Only reroute if the new route is faster than the current route by the given TIME |
| device.rerouting.with-taz | BOOL | false | Use zones (districts) as routing start- and endpoints |
| device.rerouting.mode | STR | 0 | Set routing flags (8 ignores temporary blockages) |
| device.rerouting.init-with-loaded-weights | BOOL | false | Use weight files given with option --weight-files for initializing edge weights |
| device.rerouting.threads | INT | 0 | The number of parallel execution threads used for rerouting |
| device.rerouting.synchronize | BOOL | false | Let rerouting happen at the same time for all vehicles |
| device.rerouting.railsignal | BOOL | false | Allow rerouting triggered by rail signals. |
| device.rerouting.bike-speeds | BOOL | false | Compute separate average speeds for bicycles |
| device.rerouting.output | FILE |  | Save adapting weights to FILE |
| person-device.rerouting.probability | FLOAT | -1 | The probability for a person to have a &apos;rerouting&apos; device |
| person-device.rerouting.explicit | STR[] |  | Assign a &apos;rerouting&apos; device to named persons |
| person-device.rerouting.deterministic | BOOL | false | The &apos;rerouting&apos; devices are set deterministic using a fraction of 1000 |
| person-device.rerouting.period | TIME | 0 | The period with which the person shall be rerouted |
| person-device.rerouting.mode | STR | 0 | Set routing flags (8 ignores temporary blockages) |
| person-device.rerouting.scope | STR | stage | Which part of the person plan is to be replaced (stage, sequence, or trip) |

## Registros, avisos e erros (report)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| verbose | BOOL | false | Switches to verbose output |
| print-options | BOOL | false | Prints option values before processing |
| help | BOOL | false | Prints this screen or selected topics |
| version | BOOL | false | Prints the current version |
| xml-validation | STR | local | Set schema validation scheme of XML inputs (&quot;never&quot;, &quot;local&quot;, &quot;auto&quot; or &quot;always&quot;) |
| xml-validation.net | STR | never | Set schema validation scheme of SUMO network inputs (&quot;never&quot;, &quot;local&quot;, &quot;auto&quot; or &quot;always&quot;) |
| xml-validation.routes | STR | local | Set schema validation scheme of SUMO route inputs (&quot;never&quot;, &quot;local&quot;, &quot;auto&quot; or &quot;always&quot;) |
| no-warnings | BOOL | false | Disables output of warnings |
| aggregate-warnings | INT | -1 | Aggregate warnings of the same type whenever more than INT occur |
| log | FILE |  | Writes all messages to FILE (implies verbose) |
| message-log | FILE |  | Writes all non-error messages to FILE (implies verbose) |
| error-log | FILE |  | Writes all warnings and errors to FILE |
| log.timestamps | BOOL | false | Writes timestamps in front of all messages |
| log.processid | BOOL | false | Writes process ID in front of all messages |
| language | STR | C | Language to use in messages |
| duration-log.disable | BOOL | false | Disable performance reports for individual simulation steps |
| duration-log.statistics | BOOL | false | Enable statistics on vehicle trips |
| no-step-log | BOOL | false | Disable console output of current simulation step |
| step-log.period | INT | 100 | Number of simulation steps between step-log outputs |

## Modelos de emissões (emissions)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| emissions.volumetric-fuel | BOOL | false | Return fuel consumption values in (legacy) unit l instead of mg |
| phemlight-path | FILE | ./PHEMlight/ | Determines where to load PHEMlight definitions from |
| phemlight-year | INT | 0 | Enable fleet age modelling with the given reference year in PHEMlight5 |
| phemlight-temperature | FLOAT | 1.79769e+308 | Set ambient temperature to correct NOx emissions in PHEMlight5 |
| device.emissions.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;emissions&apos; device |
| device.emissions.explicit | STR[] |  | Assign a &apos;emissions&apos; device to named vehicles |
| device.emissions.deterministic | BOOL | false | The &apos;emissions&apos; devices are set deterministic using a fraction of 1000 |
| device.emissions.begin | STR | -1 | Recording begin time for emission-data |
| device.emissions.period | STR | 0 | Recording period for emission-output |

## Comunicação entre veículos (communication)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| device.btreceiver.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;btreceiver&apos; device |
| device.btreceiver.explicit | STR[] |  | Assign a &apos;btreceiver&apos; device to named vehicles |
| device.btreceiver.deterministic | BOOL | false | The &apos;btreceiver&apos; devices are set deterministic using a fraction of 1000 |
| device.btreceiver.range | FLOAT | 300 | The range of the bt receiver |
| device.btreceiver.all-recognitions | BOOL | false | Whether all recognition point shall be written |
| device.btreceiver.offtime | FLOAT | 0.64 | The offtime used for calculating detection probability (in seconds) |
| device.btsender.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;btsender&apos; device |
| device.btsender.explicit | STR[] |  | Assign a &apos;btsender&apos; device to named vehicles |
| device.btsender.deterministic | BOOL | false | The &apos;btsender&apos; devices are set deterministic using a fraction of 1000 |
| person-device.btsender.probability | FLOAT | -1 | The probability for a person to have a &apos;btsender&apos; device |
| person-device.btsender.explicit | STR[] |  | Assign a &apos;btsender&apos; device to named persons |
| person-device.btsender.deterministic | BOOL | false | The &apos;btsender&apos; devices are set deterministic using a fraction of 1000 |
| person-device.btreceiver.probability | FLOAT | -1 | The probability for a person to have a &apos;btreceiver&apos; device |
| person-device.btreceiver.explicit | STR[] |  | Assign a &apos;btreceiver&apos; device to named persons |
| person-device.btreceiver.deterministic | BOOL | false | The &apos;btreceiver&apos; devices are set deterministic using a fraction of 1000 |

## Baterias e energia (battery)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| device.stationfinder.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;stationfinder&apos; device |
| device.stationfinder.explicit | STR[] |  | Assign a &apos;stationfinder&apos; device to named vehicles |
| device.stationfinder.deterministic | BOOL | false | The &apos;stationfinder&apos; devices are set deterministic using a fraction of 1000 |
| device.stationfinder.rescueTime | TIME | 1800 | Time to wait for a rescue vehicle on the road side when the battery is empty |
| device.stationfinder.rescueAction | STR | remove | How to deal with a vehicle which has to stop due to low battery: [none, remove, tow] |
| device.stationfinder.reserveFactor | FLOAT | 1.1 | Scale battery need with this factor to account for unexpected traffic situations |
| device.stationfinder.emptyThreshold | FLOAT | 0.05 | Battery percentage to go into rescue mode |
| device.stationfinder.radius | TIME | 180 | Search radius in travel time seconds |
| device.stationfinder.maxEuclideanDistance | FLOAT | -1 | Euclidean search distance in meters (a negative value disables the restriction) |
| device.stationfinder.repeat | TIME | 60 | When to trigger a new search if no station has been found |
| device.stationfinder.maxChargePower | FLOAT | 100000 | The maximum charging speed of the vehicle battery |
| device.stationfinder.chargeType | STR | charging | Type of energy transfer |
| device.stationfinder.waitForCharge | TIME | 600 | After this waiting time vehicle searches for a new station when the initial one is blocked |
| device.stationfinder.minOpportunityDuration | TIME | 3600 | Only stops with a predicted duration of at least the given threshold are considered for opportunistic charging. |
| device.stationfinder.saturatedChargeLevel | FLOAT | 0.8 | Target state of charge after which the vehicle stops charging |
| device.stationfinder.needToChargeLevel | FLOAT | 0.4 | State of charge the vehicle begins searching for charging stations |
| device.stationfinder.opportunisticChargeLevel | FLOAT | 0 | State of charge below which the vehicle may look for charging opportunities along its planned stops |
| device.stationfinder.replacePlannedStop | FLOAT | 0 | Share of stopping time of the next independently planned stop to use for charging instead |
| device.stationfinder.maxDistanceToReplacedStop | FLOAT | 300 | Maximum distance in meters from the original stop to be replaced by the charging stop |
| device.stationfinder.chargingStrategy | STR | none | Set a charging strategy to alter time and charging load from the set: [none, balanced, latest] |
| device.stationfinder.checkEnergyForRoute | BOOL | true | Only search for charging stations if the battery charge is not estimated sufficient to complete the current route |
| device.battery.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;battery&apos; device |
| device.battery.explicit | STR[] |  | Assign a &apos;battery&apos; device to named vehicles |
| device.battery.deterministic | BOOL | false | The &apos;battery&apos; devices are set deterministic using a fraction of 1000 |
| device.battery.track-fuel | BOOL | false | Track fuel consumption for non-electric vehicles |

## Dispositivo de exemplo (example_device)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| device.example.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;example&apos; device |
| device.example.explicit | STR[] |  | Assign a &apos;example&apos; device to named vehicles |
| device.example.deterministic | BOOL | false | The &apos;example&apos; devices are set deterministic using a fraction of 1000 |
| device.example.parameter | FLOAT | 0 | An exemplary parameter which can be used by all instances of the example device |

## Indicadores de conflito e segurança (ssm_device)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| device.ssm.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;ssm&apos; device |
| device.ssm.explicit | STR[] |  | Assign a &apos;ssm&apos; device to named vehicles |
| device.ssm.deterministic | BOOL | false | The &apos;ssm&apos; devices are set deterministic using a fraction of 1000 |
| device.ssm.measures | STR |  | Specifies which measures will be logged (as a space or comma-separated sequence of IDs in (&apos;TTC&apos;, &apos;DRAC&apos;, &apos;PET&apos;, &apos;PPET&apos;, &apos;MDRAC&apos;)) |
| device.ssm.thresholds | STR |  | Specifies space or comma-separated thresholds corresponding to the specified measures (see documentation and watch the order!). Only events exceeding the thresholds will be logged. |
| device.ssm.trajectories | BOOL | false | Specifies whether trajectories will be logged (if false, only the extremal values and times are reported). |
| device.ssm.range | FLOAT | 50 | Specifies the detection range in meters. For vehicles below this distance from the equipped vehicle, SSM values are traced. |
| device.ssm.extratime | FLOAT | 5 | Specifies the time in seconds to be logged after a conflict is over. Required &gt;0 if PET is to be calculated for crossing conflicts. |
| device.ssm.mdrac.prt | FLOAT | 1 | Specifies the perception reaction time for MDRAC computation. |
| device.ssm.file | STR |  | Give a global default filename for the SSM output |
| device.ssm.geo | BOOL | false | Whether to use coordinates of the original reference system in output |
| device.ssm.write-positions | BOOL | false | Whether to write positions (coordinates) for each timestep |
| device.ssm.write-lane-positions | BOOL | false | Whether to write lanes and their positions for each timestep |
| device.ssm.write-na | BOOL | true | Whether to write conflict outputs with no data as NA values or skip it |
| device.ssm.exclude-conflict-types | STR |  | Which conflicts will be excluded from the log according to the conflict type they have been classified (combination of values in &apos;ego&apos;, &apos;foe&apos; , &apos;&apos;, any numerical valid conflict type code). An empty value will log all and &apos;ego&apos;/&apos;foe&apos; refer to a certain conflict type subset. |

## Transição do controle do veículo (toc_device)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| device.toc.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;toc&apos; device |
| device.toc.explicit | STR[] |  | Assign a &apos;toc&apos; device to named vehicles |
| device.toc.deterministic | BOOL | false | The &apos;toc&apos; devices are set deterministic using a fraction of 1000 |
| device.toc.manualType | STR |  | Vehicle type for manual driving regime. |
| device.toc.automatedType | STR |  | Vehicle type for automated driving regime. |
| device.toc.responseTime | FLOAT | -1 | Average response time needed by a driver to take back control. |
| device.toc.recoveryRate | FLOAT | 0.1 | Recovery rate for the driver&apos;s awareness after a ToC. |
| device.toc.lcAbstinence | FLOAT | 0 | Attention level below which a driver restrains from performing lane changes (value in [0,1]). |
| device.toc.initialAwareness | FLOAT | 0.5 | Average awareness a driver has initially after a ToC (value in [0,1]). |
| device.toc.mrmDecel | FLOAT | 1.5 | Deceleration rate applied during a &apos;minimum risk maneuver&apos;. |
| device.toc.dynamicToCThreshold | FLOAT | 0 | Time, which the vehicle requires to have ahead to continue in automated mode. The default value of 0 indicates no dynamic triggering of ToCs. |
| device.toc.dynamicMRMProbability | FLOAT | 0.05 | Probability that a dynamically triggered TOR is not answered in time. |
| device.toc.mrmKeepRight | BOOL | false | If true, the vehicle tries to change to the right during an MRM. |
| device.toc.mrmSafeSpot | STR |  | If set, the vehicle tries to reach the given named stopping place during an MRM. |
| device.toc.mrmSafeSpotDuration | FLOAT | 60 | Duration the vehicle stays at the safe spot after an MRM. |
| device.toc.maxPreparationAccel | FLOAT | 0 | Maximal acceleration that may be applied during the ToC preparation phase. |
| device.toc.ogNewTimeHeadway | FLOAT | -1 | Timegap for ToC preparation phase. |
| device.toc.ogNewSpaceHeadway | FLOAT | -1 | Additional spacing for ToC preparation phase. |
| device.toc.ogMaxDecel | FLOAT | -1 | Maximal deceleration applied for establishing increased gap in ToC preparation phase. |
| device.toc.ogChangeRate | FLOAT | -1 | Rate of adaptation towards the increased headway during ToC preparation. |
| device.toc.useColorScheme | BOOL | true | Whether a coloring scheme shall by applied to indicate the different ToC stages. |
| device.toc.file | STR |  | Switches on output by specifying an output filename. |

## Estado do motorista (driver_state_device)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| device.driverstate.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;driverstate&apos; device |
| device.driverstate.explicit | STR[] |  | Assign a &apos;driverstate&apos; device to named vehicles |
| device.driverstate.deterministic | BOOL | false | The &apos;driverstate&apos; devices are set deterministic using a fraction of 1000 |
| device.driverstate.initialAwareness | FLOAT | 1 | Initial value assigned to the driver&apos;s awareness. |
| device.driverstate.errorTimeScaleCoefficient | FLOAT | 100 | Time scale for the error process. |
| device.driverstate.errorNoiseIntensityCoefficient | FLOAT | 0.2 | Noise intensity driving the error process. |
| device.driverstate.speedDifferenceErrorCoefficient | FLOAT | 0.15 | General scaling coefficient for applying the error to the perceived speed difference (error also scales with distance). |
| device.driverstate.headwayErrorCoefficient | FLOAT | 0.75 | General scaling coefficient for applying the error to the perceived distance (error also scales with distance). |
| device.driverstate.freeSpeedErrorCoefficient | FLOAT | 0 | General scaling coefficient for applying the error to the vehicle&apos;s own speed when driving without a leader (error also scales with own speed). |
| device.driverstate.speedDifferenceChangePerceptionThreshold | FLOAT | 0.1 | Base threshold for recognizing changes in the speed difference (threshold also scales with distance). |
| device.driverstate.headwayChangePerceptionThreshold | FLOAT | 0.1 | Base threshold for recognizing changes in the headway (threshold also scales with distance). |
| device.driverstate.minAwareness | FLOAT | 0.1 | Minimal admissible value for the driver&apos;s awareness. |
| device.driverstate.maximalReactionTime | FLOAT | -1 | Maximal reaction time (~action step length) induced by decreased awareness level (reached for awareness=minAwareness). |

## Veículos de emergência (bluelight_device)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| device.bluelight.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;bluelight&apos; device |
| device.bluelight.explicit | STR[] |  | Assign a &apos;bluelight&apos; device to named vehicles |
| device.bluelight.deterministic | BOOL | false | The &apos;bluelight&apos; devices are set deterministic using a fraction of 1000 |
| device.bluelight.reactiondist | FLOAT | 25 | Set the distance at which other drivers react to the blue light and siren sound |
| device.bluelight.mingapfactor | FLOAT | 1 | Reduce the minGap for reacting vehicles by the given factor |

## Dados de posição e movimento (fcd_device)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| device.fcd.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;fcd&apos; device |
| device.fcd.explicit | STR[] |  | Assign a &apos;fcd&apos; device to named vehicles |
| device.fcd.deterministic | BOOL | false | The &apos;fcd&apos; devices are set deterministic using a fraction of 1000 |
| device.fcd.begin | STR | -1 | Recording begin time for FCD-data |
| device.fcd.period | STR | 0 | Recording period for FCD-data |
| device.fcd.radius | FLOAT | 0 | Record objects in a radius around equipped vehicles |
| person-device.fcd.probability | FLOAT | -1 | The probability for a person to have a &apos;fcd&apos; device |
| person-device.fcd.explicit | STR[] |  | Assign a &apos;fcd&apos; device to named persons |
| person-device.fcd.deterministic | BOOL | false | The &apos;fcd&apos; devices are set deterministic using a fraction of 1000 |
| person-device.fcd.period | STR | 0 | Recording period for FCD-data |

## Veículos elétricos híbridos (elechybrid_device)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| device.elechybrid.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;elechybrid&apos; device |
| device.elechybrid.explicit | STR[] |  | Assign a &apos;elechybrid&apos; device to named vehicles |
| device.elechybrid.deterministic | BOOL | false | The &apos;elechybrid&apos; devices are set deterministic using a fraction of 1000 |

## Operação de táxis (taxi_device)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| device.taxi.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;taxi&apos; device |
| device.taxi.explicit | STR[] |  | Assign a &apos;taxi&apos; device to named vehicles |
| device.taxi.deterministic | BOOL | false | The &apos;taxi&apos; devices are set deterministic using a fraction of 1000 |
| device.taxi.dispatch-algorithm | STR | greedy | The dispatch algorithm [greedy\|greedyClosest\|greedyShared\|routeExtension\|traci] |
| device.taxi.dispatch-algorithm.output | FILE |  | Write information from the dispatch algorithm to FILE |
| device.taxi.dispatch-algorithm.params | STR |  | Load dispatch algorithm parameters in format KEY1:VALUE1[,KEY2:VALUE] |
| device.taxi.dispatch-period | TIME | 60 | The period between successive calls to the dispatcher |
| device.taxi.dispatch-keep-unreachable | TIME | 3600 | The time before aborting unreachable reservations |
| device.taxi.idle-algorithm | STR | stop | The behavior of idle taxis [stop\|randomCircling\|taxistand] |
| device.taxi.idle-algorithm.output | FILE |  | Write information from the idling algorithm to FILE |
| device.taxi.vclasses | STR[] | taxi | Network permissions that can be accessed by taxis |

## Recomendação de velocidade para semáforos (glosa_device)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| device.glosa.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;glosa&apos; device |
| device.glosa.explicit | STR[] |  | Assign a &apos;glosa&apos; device to named vehicles |
| device.glosa.deterministic | BOOL | false | The &apos;glosa&apos; devices are set deterministic using a fraction of 1000 |
| device.glosa.range | FLOAT | 100 | The communication range to the traffic light |
| device.glosa.max-speedfactor | FLOAT | 1.1 | The maximum speed factor when approaching a green light |
| device.glosa.min-speed | FLOAT | 5 | Minimum speed when coasting towards a red light |
| device.glosa.add-switchtime | FLOAT | 0 | Additional time the vehicle shall need to reach the intersection after the signal turns green |
| device.glosa.use-queue | BOOL | false | Use queue in front of the tls for GLOSA calculation |
| device.glosa.override-safety | BOOL | false | Override safety features - ignore the current light state, always follow GLOSA&apos;s predicted state |
| device.glosa.ignore-cfmodel | BOOL | false | Vehicles follow a perfect speed calculation - ignore speed calculations from the CF model if not safety critical |

## Informações das viagens (tripinfo_device)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| device.tripinfo.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;tripinfo&apos; device |
| device.tripinfo.explicit | STR[] |  | Assign a &apos;tripinfo&apos; device to named vehicles |
| device.tripinfo.deterministic | BOOL | false | The &apos;tripinfo&apos; devices are set deterministic using a fraction of 1000 |

## Registro das rotas percorridas (vehroutes_device)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| device.vehroute.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;vehroute&apos; device |
| device.vehroute.explicit | STR[] |  | Assign a &apos;vehroute&apos; device to named vehicles |
| device.vehroute.deterministic | BOOL | false | The &apos;vehroute&apos; devices are set deterministic using a fraction of 1000 |

## Atrito da pista (friction_device)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| device.friction.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;friction&apos; device |
| device.friction.explicit | STR[] |  | Assign a &apos;friction&apos; device to named vehicles |
| device.friction.deterministic | BOOL | false | The &apos;friction&apos; devices are set deterministic using a fraction of 1000 |
| device.friction.stdDev | FLOAT | 0.1 | The measurement noise parameter which can be applied to the friction device |
| device.friction.offset | FLOAT | 0 | The measurement offset parameter which can be applied to the friction device -&gt; e.g. to force false measurements |

## Reprodução de trajetórias (fcd_replay_device)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| device.fcd-replay.probability | FLOAT | -1 | The probability for a vehicle to have a &apos;fcd-replay&apos; device |
| device.fcd-replay.explicit | STR[] |  | Assign a &apos;fcd-replay&apos; device to named vehicles |
| device.fcd-replay.deterministic | BOOL | false | The &apos;fcd-replay&apos; devices are set deterministic using a fraction of 1000 |
| device.fcd-replay.file | FILE |  | FCD file to read |

## Servidor TraCI (traci_server)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| remote-port | INT | 0 | Enables TraCI Server if set |
| num-clients | INT | 1 | Expected number of connecting clients |

## Simulação mesoscópica (mesoscopic)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| mesosim | BOOL | false | Enables mesoscopic simulation |
| meso-edgelength | FLOAT | 98 | Length of an edge segment in mesoscopic simulation |
| meso-tauff | TIME | 1.13 | Factor for calculating the net free-free headway time |
| meso-taufj | TIME | 1.13 | Factor for calculating the net free-jam headway time |
| meso-taujf | TIME | 1.73 | Factor for calculating the jam-free headway time |
| meso-taujj | TIME | 1.4 | Factor for calculating the jam-jam headway time |
| meso-jam-threshold | FLOAT | -1 | Minimum percentage of occupied space to consider a segment jammed. A negative argument causes thresholds to be computed based on edge speed and tauff (default) |
| meso-multi-queue | BOOL | true | Enable multiple queues at edge ends |
| meso-lane-queue | BOOL | false | Enable separate queues for every lane |
| meso-ignore-lanes-by-vclass | STR[] | pedestrian,bicycle | Do not build queues (or reduce capacity) for lanes allowing only the given vclasses |
| meso-junction-control | BOOL | false | Enable mesoscopic traffic light and priority junction handling |
| meso-junction-control.limited | BOOL | false | Enable mesoscopic traffic light and priority junction handling for saturated links. This prevents faulty traffic lights from hindering flow in low-traffic situations |
| meso-tls-penalty | FLOAT | 0 | Apply scaled travel time penalties when driving across tls controlled junctions based on green split instead of checking actual phases |
| meso-tls-flow-penalty | FLOAT | 0 | Apply scaled headway penalties when driving across tls controlled junctions based on green split instead of checking actual phases |
| meso-minor-penalty | TIME | 0 | Apply fixed time penalty when driving across a minor link. When using --meso-junction-control.limited, the penalty is not applied whenever limited control is active. |
| meso-overtaking | BOOL | false | Enable mesoscopic overtaking |
| meso-recheck | TIME | 0 | Time interval for rechecking insertion into the next segment after failure |
| meso-interpolate-pos | BOOL | false | Enable mesoscopic position interpolation |

## Geração aleatória (random_number)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| random | BOOL | false | Initialises the random number generator with the current system time |
| seed | INT | 23423 | Initialises the random number generator with the given value |
| thread-rngs | INT | 64 | Number of pre-allocated random number generators to ensure repeatable multi-threaded simulations (should be at least the number of threads for repeatable simulations). |

## Interface gráfica SUMO (gui_only)

| Opção | Tipo | Padrão | Descrição SUMO |
| --- | --- | --- | --- |
| gui-settings-file | FILE |  | Load visualisation settings from FILE |
| quit-on-end | BOOL | false | Quits the GUI when the simulation stops |
| game | BOOL | false | Start the GUI in gaming mode |
| game.mode | STR | tls | Select the game type (&apos;tls&apos;, &apos;drt&apos;) |
| start | BOOL | false | Start the simulation after loading |
| delay | FLOAT | 0 | Use FLOAT in ms as delay between simulation steps |
| breakpoints | STR[] |  | Use TIME[] as times when the simulation should halt |
| edgedata-files | FILE |  | Load edge/lane weights for visualization from FILE |
| alternative-net-file | FILE |  | Load a secondary road network for abstract visualization from FILE |
| selection-file | FILE |  | Load pre-selected elements from FILE |
| demo | BOOL | false | Restart the simulation after ending (demo mode) |
| disable-textures | BOOL | false | Do not load background pictures |
| registry-viewport | BOOL | false | Load current viewport from registry |
| window-size | STR[] |  | Create initial window with the given x,y size |
| window-pos | STR[] |  | Create initial window at the given x,y position |
| tracker-interval | TIME | 1 | The aggregation period for value tracker windows |
| gui-testing | BOOL | false | Enable overlay for screen recognition |
| gui-testing-debug | BOOL | false | Enable output messages during GUI-Testing |
| gui-testing.setting-output | FILE |  | Save gui settings in the given settings output file |
