
const mongoose = require('mongoose');
const userSchema = new mongoose.Schema({ email: String });
userSchema.pre('save', function(next) { console.log('hashing...'); next(); });
module.exports = mongoose.model('User', userSchema);
