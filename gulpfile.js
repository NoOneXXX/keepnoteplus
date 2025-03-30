const { src, dest, series, parallel } = require('gulp');
const del = require('del');

// 定义要复制的文件
const thirdPartyFiles = [
    'node_modules/bootstrap/dist/**/*.*',
    'node_modules/jquery/dist/**/*.*',
    'node_modules/backbone/backbone*.js',
    'node_modules/react/*.js',
    'node_modules/wysihtml/dist/**/*.*',
    'node_modules/wysihtml/parser_rules/advanced_and_extended.js',
    'node_modules/xmldom/dom.js'
];

// 清理任务
function clean() {
    return del(['keepnote/server/static/thirdparty/**']);
}

// 构建任务
function buildThirdParty() {
    return src(thirdPartyFiles, { base: 'node_modules' })
        .pipe(dest('keepnote/server/static/thirdparty/'));
}

// 默认任务
exports.clean = clean;
exports.build = buildThirdParty;
exports.default = series(clean, buildThirdParty);