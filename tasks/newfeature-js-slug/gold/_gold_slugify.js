const _ = require('lodash');

function slugify(name) {
  return _.kebabCase(name);
}

module.exports = { slugify };
