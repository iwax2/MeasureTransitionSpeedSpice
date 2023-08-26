import sys
import re

VDD_VOLTAGE = 1.8
GND_VOLTAGE = 0
PULSE_MIN_VOLTAGE = (VDD_VOLTAGE - GND_VOLTAGE) * 0.1
PULSE_MID_VOLTAGE = (VDD_VOLTAGE - GND_VOLTAGE) * 0.5
PULSE_MAX_VOLTAGE = (VDD_VOLTAGE - GND_VOLTAGE) * 0.9
# spice遷移解析のステップ    ms     us     ns     ps
TRANSITION_ANALYSIS_STEP =  1000 * 1000 * 1000 * 1000 # ps表示(10^12)がデフォルト
SEAQUENTIAL_AREA_THREASHOLD = 10
DEBUG = False

if( (len(sys.argv) < 2) ):
    print("usage:", sys.argv[0], '<HSPICE_LOG_FILE> [MEASURE_NODE_NAME]')

hspice_log_path = sys.argv[1].replace('\\','/')
target_module   = hspice_log_path
if( target_module.rfind('/') >= 0 ):
    target_module = target_module[target_module.rfind('/')+1:]
if( target_module.find('.') >= 0 ):
    target_module = target_module[0:target_module.find('.')]
print('Target module is : ', target_module)

measure_node_name = ''
if( (len(sys.argv) > 2) ):
    measure_node_name = sys.argv[2]

warning_log = []
transition_log = []
measure_target = []
node_names = []
max_voltage = sys.float_info.min
min_voltage = sys.float_info.max

def expfloat2int(str):
    d = str.replace(' ','').split('e')
    e = int(d[1])
    f = int(d[0].replace('.','')) 
    r = int(f * pow(10, 12+e-4))
    return(r)

with open(hspice_log_path) as f:
    pattern_node_count = re.compile('\s*time\s*[\s\w]+')
    pv = '([-\d\.]+e[+-]\d+)\s*'
    pattern_transition_result = re.compile(pv)
    seq_count = 0
    prev_data = {}
    ps_holder = 0
    ps_counter = 0
    for line in f:
        line = line.rstrip()
        m = pattern_transition_result.match(line)
        if( '**warning**' in line ):
            warning_log.append(line)
        if( pattern_node_count.match(line)):
            measure_target = line.split()
            node_names = f.readline().rstrip().split()
            node_names.insert(0, 'T')
            measure_node_name = node_names[len(node_names)-1]
            prev_data[measure_node_name] = 0
            if( len(measure_target) != len(node_names) ):
                print("Error: node analyze failed.", measure_target, node_names)
            pattern = '\s*' + pv * len(measure_target)
            pattern_transition_result = re.compile(pattern)
        if(m):
            data = {}
            for i, n in enumerate(node_names):
                if( n=='T' ):
                    v = expfloat2int(m.group(i+1)) # ps表示に変更
                else:
                    v = float(m.group(i+1))
                # print(n, measure_target[i], v)
                data[n] = v
                if( v > max_voltage ):
                    max_voltage = v
                elif( v < min_voltage ):
                    min_voltage = v
            # なんと100ns以上シミュレーションすると1ps単位が四捨五入されて消えてしまう
            if( data['T'] >= 100*1000 ):
                if( ps_holder == data['T']):
                    ps_counter += 1
                else:
                    ps_counter = 0
                ps_holder = data['T']
                data['T'] += ps_counter
                # print(data['T'])
            # if( prev_data[measure_node_name] == data[measure_node_name] ):
            #     if( seq_count < SEAQUENTIAL_AREA_THREASHOLD ):
            #         seq_count += 1
            #         transition_log.append(data)
            # elif( seq_count >= SEAQUENTIAL_AREA_THREASHOLD ):
            #     transition_log.append(prev_data)
            #     transition_log.append(data)
            #     seq_count = 0
            # prev_data = data
            transition_log.append(data)


# print(max_voltage, min_voltage)
def find_input_transition(i):
    data = transition_log[i]
    input_node = node_names.copy()
    input_node.remove('T')
    input_node.remove(measure_node_name)
    j=1
    while(i>j):
        # print(j, data, transition_log[i-j])
        for n in input_node:
            if( data[n] > transition_log[i-j][n] ):
                if( transition_log[i-j][n] < PULSE_MID_VOLTAGE ):
                    # print(transition_log[i-j+1])
                    return(transition_log[i-j+1])
            elif( data[n] < transition_log[i-j][n] ):
                if( transition_log[i-j][n] > PULSE_MID_VOLTAGE ):
                    # print(transition_log[i-j+1])
                    return(transition_log[i-j+1])
        j+=1

rise_flag = False
fall_flag = False
delay_r_flag = False
delay_f_flag = False
tr1 = 0
tr2 = 0
tf1 = 0
tf2 = 0
tdr1 = 0
tdr2 = 0
tdf1 = 0
tdf2 = 0
for i, data in enumerate(transition_log):
    target = data[measure_node_name]
    if( target > PULSE_MAX_VOLTAGE ):
        # print("Stable high level", data)
        if( rise_flag ):
            tr2 = data
            if DEBUG : print('Tr1 =', tr1, 'Tr2 =', tr2)
            print('Rising transition time "tr" is', tr2['T']-tr1['T'])
        rise_flag = False
        fall_flag = False
        delay_r_flag = False
        delay_f_flag = False
        # if( target >= max_voltage ):
        #     print('Max:', data)
    elif( target < PULSE_MIN_VOLTAGE ):
        # print("Stable low level", data)
        if( fall_flag ):
            tf2 = data
            if DEBUG : print('Tf1 =', tf1, 'Tf2 =', tf2)
            print('Falling transition time "tf" is', tf2['T']-tf1['T'])
        rise_flag = False
        fall_flag = False
        delay_r_flag = False
        delay_f_flag = False
        # if( target <= min_voltage ):
        #     print('Min:', data)
    else:
        if( target > transition_log[i-SEAQUENTIAL_AREA_THREASHOLD][measure_node_name] ):
            # print("Rise transition now", data)
            if( not rise_flag ):
                tr1 = data
            if( not delay_r_flag and target >= PULSE_MID_VOLTAGE ):
                tdr2 = data
                delay_r_flag = True
                tdr1 = find_input_transition(i)
                if DEBUG : print('Tdr1 =', tdr1, 'Tdr2 =', tdr2)
                print('Rising transition delay time "tdr" is', tdr2['T']-tdr1['T'])
            rise_flag = True
            fall_flag = False
 
                
        elif( target < transition_log[i-SEAQUENTIAL_AREA_THREASHOLD][measure_node_name] ):
            # print("Fall transition now", data)
            if( not fall_flag ):
                tf1 = data
            if( not delay_f_flag and target <= PULSE_MID_VOLTAGE ):
                tdf2 = data
                delay_f_flag = True
                tdf1 = find_input_transition(i)
                if DEBUG : print('Tdf1 =', tdf1, 'Tdf2 =', tdf2)
                print('Falling transition delay time "tdf" is', tdf2['T']-tdf1['T'])
            rise_flag = False
            fall_flag = True
    # print(data)




