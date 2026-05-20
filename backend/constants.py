COPTER_MODES = {
    0: '自稳', 1: '特技', 2: '定高', 3: '自动', 4: '引导',
    5: '悬停', 6: '返航', 7: '绕圈', 9: '降落', 16: '定点', 21: '智能返航',
}
PLANE_MODES = {
    0: '手动', 1: '绕圈', 2: '自稳', 5: '辅助A', 6: '辅助B', 7: '巡航',
    10: '自动', 11: '返航', 12: '盘旋', 15: '引导',
    17: '旋翼自稳', 18: '旋翼悬停', 19: '旋翼定点', 20: '旋翼降落', 21: '旋翼返航',
}
ROVER_MODES = {
    0: '手动', 1: '特技', 3: '转向', 4: '固定', 5: '跟随',
    10: '自动', 11: '返航', 12: '智能返航', 15: '引导',
}
SUB_MODES = {
    0: '自稳', 1: '特技', 2: '定深', 3: '自动', 4: '引导',
    7: '绕圈', 9: '水面', 16: '定点', 19: '手动',
}
COPTER_BTNS = [[0, '自稳'], [2, '定高'], [5, '悬停'], [3, '自动'], [6, '返航'], [9, '降落']]
PLANE_BTNS = [
    [19, '旋翼定点'], [18, '旋翼悬停'], [17, '旋翼自稳'],
    [10, '自动'], [21, '旋翼返航'], [20, '旋翼降落'], [12, '盘旋'], [11, '返航'],
]
ROVER_BTNS = [[0, '手动'], [4, '固定'], [10, '自动'], [15, '引导'], [11, '返航']]
SUB_BTNS = [[0, '自稳'], [2, '定深'], [16, '定点'], [3, '自动'], [4, '引导']]
FIX_NAMES = {0: '无定位', 1: '无定位', 2: '2D', 3: '3D', 4: '差分', 5: 'RTK浮动', 6: 'RTK固定'}

COPTER_MODES_EN = {
    0: 'Stabilize', 1: 'Acro', 2: 'Alt Hold', 3: 'Auto', 4: 'Guided',
    5: 'Loiter', 6: 'RTL', 7: 'Circle', 9: 'Land', 16: 'PosHold', 21: 'Smart RTL',
}
PLANE_MODES_EN = {
    0: 'Manual', 1: 'Circle', 2: 'Stabilize', 5: 'FBW-A', 6: 'FBW-B', 7: 'Cruise',
    10: 'Auto', 11: 'RTL', 12: 'Loiter', 15: 'Guided',
    17: 'Q-Stabilize', 18: 'Q-Hover', 19: 'Q-Loiter', 20: 'Q-Land', 21: 'Q-RTL',
}
ROVER_MODES_EN = {
    0: 'Manual', 1: 'Acro', 3: 'Steering', 4: 'Hold', 5: 'Follow',
    10: 'Auto', 11: 'RTL', 12: 'Smart RTL', 15: 'Guided',
}
SUB_MODES_EN = {
    0: 'Stabilize', 1: 'Acro', 2: 'Depth Hold', 3: 'Auto', 4: 'Guided',
    7: 'Circle', 9: 'Surface', 16: 'PosHold', 19: 'Manual',
}
COPTER_BTNS_EN = [[0, 'Stabilize'], [2, 'Alt Hold'], [5, 'Loiter'], [3, 'Auto'], [6, 'RTL'], [9, 'Land']]
PLANE_BTNS_EN = [
    [19, 'Q-Loiter'], [18, 'Q-Hover'], [17, 'Q-Stabilize'],
    [10, 'Auto'], [21, 'Q-RTL'], [20, 'Q-Land'], [12, 'Loiter'], [11, 'RTL'],
]
ROVER_BTNS_EN = [[0, 'Manual'], [4, 'Hold'], [10, 'Auto'], [15, 'Guided'], [11, 'RTL']]
SUB_BTNS_EN = [[0, 'Stabilize'], [2, 'Depth Hold'], [16, 'PosHold'], [3, 'Auto'], [4, 'Guided']]
FIX_NAMES_EN = {0: 'No Fix', 1: 'No Fix', 2: '2D', 3: '3D', 4: 'DGPS', 5: 'RTK Float', 6: 'RTK Fixed'}
